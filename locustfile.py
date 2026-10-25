"""Нагрузочное тестирование API электронной торговой площадки «ТоргЛайн» (курсовой проект).

Четыре вида виртуальных пользователей:
  Guest     - гость листает каталог в случайном порядке (TaskSet);
  Buyer     - покупатель смотрит свои торги и делает ставки (TaskSet);
  Seller    - продавец просматривает свои лоты и выставляет новые (TaskSet);
  Newcomer  - новый пользователь проходит регистрацию шаг за шагом (SequentialTaskSet).

У каждого GET-задания вес не меньше 5, у каждого POST-задания - 1, поэтому GET выполняются минимум
в 5 раз чаще. После теста соотношение проверяется по статистике (check_ratio).
"""
import random
from datetime import datetime, timedelta, timezone

import requests
from locust import HttpUser, SequentialTaskSet, TaskSet, between, events, task

import data

PASSWORD = "TorgLine2026"  # пароль демонстрационных учетных записей курсового
SELLERS = ["seller", "s.morozov", "n.nikolaev", "k.petrov", "a.mihaylova", "t.mihaylov", "a.lebedev", "e.petrov",
           "t.stepanova", "o.stepanov", "e.novikova", "a.popova"]
BUYERS = ["buyer", "buyer2", "d.vasileva", "v.volkova", "i.lebedev", "p.kuznetsova", "s.pavlov", "o.fedorov",
          "i.sokolova", "a.mihaylov", "t.petrov", "a.alekseeva", "e.ivanova", "d.vasilev", "i.soloveva", "a.popov",
          "k.makarova", "i.popov", "k.kuznetsov", "k.makarov", "e.stepanova", "a.makarov", "a.smirnova"]

auction_ids = []      # id торгов из каталога, чтобы открывать существующие карточки
test_auction = None   # торги, созданные для теста ставок (см. prepare_auction)


def login(client, user_login):
    r = client.post("/api/auth/login", json={"login": user_login, "password": PASSWORD}, name="/api/auth/login")
    return {"Authorization": "Bearer " + r.json().get("token", "")} if r.ok else {}


@events.test_start.add_listener
def prepare_auction(environment, **_):
    """Перед тестом через API проходит полный путь лота: продавец выставляет его, модератор одобряет
    и назначает торги без задатка - покупатели сразу допускаются к ставкам."""
    global test_auction
    host = environment.host
    auth = lambda who: {"Authorization": "Bearer " + requests.post(
        f"{host}/api/auth/login", json={"login": who, "password": PASSWORD}).json()["token"]}
    lot = data.lot() | {"submit": True, "bid_step": 100}
    lot_id = requests.post(f"{host}/api/my/lots", json=lot, headers=auth("seller")).json()["id"]
    moderator = auth("moderator")
    requests.post(f"{host}/api/moderation/lots/{lot_id}/decision", json={"approve": True}, headers=moderator)
    # начало на 2 минуты раньше: часы виртуальной машины Docker могут отставать, а торги
    # с началом «в будущем» получат статус «назначены» вместо «идут»
    now = datetime.now(timezone.utc)
    r = requests.post(f"{host}/api/moderation/lots/{lot_id}/auction", headers=moderator,
                      json={"start_at": (now - timedelta(minutes=2)).isoformat(), "end_at": (now + timedelta(hours=3)).isoformat(),
                            "deposit": 0})
    test_auction = r.json()["auction_id"]
    print(f"Торги для ставок: №{test_auction} «{lot['title']}»")


@events.quitting.add_listener
def check_ratio(environment, **_):
    """GET должно быть минимум в 5 раз больше, чем POST. Если нет - код выхода 1."""
    count = {"GET": 0, "POST": 0}
    for (_, method), entry in environment.stats.entries.items():
        if method in count:
            count[method] += entry.num_requests
    ratio = count["GET"] / max(count["POST"], 1)
    print(f"GET: {count['GET']}, POST: {count['POST']}, GET/POST = {ratio:.1f}")
    if ratio < 5:
        print("Соотношение GET/POST меньше 5")
        environment.process_exit_code = 1


class CatalogTasks(TaskSet):
    """Гость ходит по каталогу без определенного порядка - подходит обычный TaskSet."""

    @task(10)
    def catalog(self):
        params = {"status": random.choice(["active,scheduled", "active", "finished"]),
                  "sort": random.choice(["end_at", "price", "bids"]), "order": random.choice(["asc", "desc"]),
                  "page": random.randint(1, 3), "size": 12}
        if random.random() < 0.4:
            params["category_id"] = random.choice(list(data.GOODS))
        r = self.client.get("/api/auctions", params=params, name="/api/auctions [фильтры]")
        if r.ok:
            auction_ids.extend(a["auction_id"] for a in r.json()["items"] if a["auction_id"] not in auction_ids)

    @task(6)
    def search(self):
        self.client.get("/api/auctions", params={"q": data.search_word(), "status": "active,scheduled,finished"},
                        name="/api/auctions [поиск]")

    @task(8)
    def card(self):
        if auction_ids:
            self.client.get(f"/api/auctions/{random.choice(auction_ids)}", name="/api/auctions/{id}")

    @task(5)
    def categories(self):
        self.client.get("/api/categories")


class BuyerTasks(TaskSet):
    def on_start(self):
        self.headers = login(self.client, random.choice(BUYERS))
        # заявка на торги; если покупатель уже подавал ее в прошлом тесте - это не ошибка
        with self.client.post(f"/api/auctions/{test_auction}/apply", json={}, headers=self.headers,
                              name="/api/auctions/{id}/apply", catch_response=True) as r:
            if r.status_code == 400 and "уже подана" in r.text:
                r.success()
            elif not r.ok:
                r.failure(r.text)

    @task(5)
    def participations(self):
        self.client.get("/api/me/participations", headers=self.headers)

    @task(5)
    def deals(self):
        self.client.get("/api/me/deals", headers=self.headers)

    @task(8)
    def watch_auction(self):
        self.client.get(f"/api/auctions/{test_auction}", name="/api/auctions/{id}")

    @task(1)
    def bid(self):
        card = self.client.get(f"/api/auctions/{test_auction}", name="/api/auctions/{id}").json()
        amount = card["min_next_bid"] + random.choice([0, 0, 1, 5]) * card["bid_step"]
        with self.client.post(f"/api/auctions/{test_auction}/bids", json={"amount": amount}, headers=self.headers,
                              name="/api/auctions/{id}/bids", catch_response=True) as r:
            # пока покупатель думал, его перебили или он уже лидирует - обычный исход торгов, а не сбой
            if r.status_code == 400 and any(t in r.text for t in ("Минимальная ставка", "лидирует")):
                r.success()
            elif not r.ok:
                r.failure(r.text)


class SellerTasks(TaskSet):
    def on_start(self):
        self.headers = login(self.client, random.choice(SELLERS))
        self.lot_ids = []

    @task(8)
    def my_lots(self):
        params = {"status": random.choice(["draft", "moderation", "approved,sold", "draft,moderation,approved"]),
                  "sort": random.choice(["created_at", "title", "start_price"]), "page": 1, "size": 20}
        r = self.client.get("/api/my/lots", params=params, headers=self.headers, name="/api/my/lots")
        if r.ok:
            self.lot_ids = [lot["id"] for lot in r.json()["items"]] or self.lot_ids

    @task(5)
    def my_lot(self):
        if self.lot_ids:
            self.client.get(f"/api/my/lots/{random.choice(self.lot_ids)}", headers=self.headers,
                            name="/api/my/lots/{id}")

    @task(5)
    def categories(self):
        self.client.get("/api/categories")

    @task(1)
    def create_lot(self):
        r = self.client.post("/api/my/lots", json=data.lot(), headers=self.headers, name="/api/my/lots [создать]")
        if r.ok:
            self.lot_ids.append(r.json()["id"])


class RegistrationFlow(SequentialTaskSet):
    """Регистрация возможна только в определенном порядке: зарегистрироваться -> войти -> работать
    с профилем. Поэтому здесь SequentialTaskSet. Вес у задания в нем означает число повторов подряд."""

    @task(1)
    def open_categories(self):
        self.client.get("/api/categories")

    @task(5)
    def browse_catalog(self):
        r = self.client.get("/api/auctions", params={"status": "active,scheduled", "page": random.randint(1, 2)},
                            name="/api/auctions [фильтры]")
        if r.ok:
            auction_ids.extend(a["auction_id"] for a in r.json()["items"] if a["auction_id"] not in auction_ids)

    @task(1)
    def register(self):
        self.user_data = data.person(random.choice(["buyer", "seller"]))
        self.client.post("/api/auth/register", json=self.user_data)

    @task(1)
    def sign_in(self):
        r = self.client.post("/api/auth/login", json={"login": self.user_data["login"],
                                                       "password": self.user_data["password"]})
        self.headers = {"Authorization": "Bearer " + r.json().get("token", "")} if r.ok else {}

    @task(1)
    def me(self):
        self.client.get("/api/auth/me", headers=self.headers)

    @task(1)
    def update_profile(self):
        self.client.put("/api/auth/profile", json=data.profile(self.user_data), headers=self.headers)

    @task(1)
    def check_profile(self):
        # новый адрес должен сохраниться
        with self.client.get("/api/auth/me", headers=self.headers, name="/api/auth/me [проверка]",
                             catch_response=True) as r:
            if r.ok and not r.json()["profile"]["address"]:
                r.failure("Адрес в профиле не сохранился")

    @task(5)
    def open_card(self):
        if auction_ids:
            self.client.get(f"/api/auctions/{random.choice(auction_ids)}", name="/api/auctions/{id}")

    @task(1)
    def own_page(self):
        if self.user_data["role"] == "buyer":
            self.client.get("/api/me/participations", headers=self.headers)
        else:
            self.client.get("/api/my/lots", headers=self.headers, name="/api/my/lots")


class Guest(HttpUser):
    weight = 6
    wait_time = between(1, 3)
    tasks = [CatalogTasks]


class Buyer(HttpUser):
    weight = 3
    wait_time = between(1, 3)
    tasks = [BuyerTasks]


class Seller(HttpUser):
    weight = 2
    wait_time = between(1, 3)
    tasks = [SellerTasks]


class Newcomer(HttpUser):
    weight = 1
    wait_time = between(1, 2)
    tasks = [RegistrationFlow]
