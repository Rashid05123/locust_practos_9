"""Генерация тестовых данных для запросов (Faker, русская локаль).

Данные должны проходить проверки API «ТоргЛайн»: логин латиницей 3-50 символов, телефон +7 и 10 цифр,
паспорт «1234 567890», пароль от 8 символов с буквами и цифрами, возраст от 18 лет.
"""
import random
import uuid

from faker import Faker

fake = Faker("ru_RU")

# Товары по категориям площадки: id категории -> (что продают, модели, цена от, цена до)
GOODS = {
    2: ("Смартфон", ["Samsung Galaxy S23", "iPhone 14", "Xiaomi Redmi Note 13", "Google Pixel 7", "Honor 90"],
        8000, 90000),
    3: ("Ноутбук", ["Lenovo ThinkPad T14", "ASUS VivoBook 15", "Apple MacBook Air M1", "HP Pavilion 15",
                    "Acer Aspire 5"], 15000, 120000),
    4: ("Фотоаппарат", ["Canon EOS 250D", "Nikon D5600", "Sony Alpha a6400", "Fujifilm X-T30"], 20000, 110000),
    5: ("Наушники", ["Sony WH-1000XM4", "JBL Tune 760NC", "Sennheiser HD 560S", "Marshall Major IV"], 3000, 30000),
    7: ("Монета", ["1 рубль 1924 г.", "50 копеек 1922 г.", "3 рубля 1987 г. «Октябрь»", "10 рублей 2010 г. ГВС"],
        500, 25000),
    9: ("Картина", ["«Зимний пейзаж», холст, масло", "«Натюрморт с яблоками», картон, масло",
                    "«Вечерний город», акварель"], 5000, 80000),
    14: ("Велосипед", ["Stels Navigator 700", "Merida Big.Nine 20", "Forward Sporting 29", "Trek Marlin 5"],
         10000, 70000),
    16: ("Часы", ["Casio G-Shock GA-2100", "Seiko 5 SNK809", "Восток Амфибия", "Orient Bambino"], 4000, 60000),
    19: ("Гитара", ["Yamaha F310", "Fender Squier Stratocaster", "Cort AD810", "Ibanez GRG121DX"], 7000, 60000),
    22: ("Палатка", ["Tramp Lite Camp 3", "Outventure Dalen 2", "Naturehike Cloud Up 2"], 4000, 25000),
}
CONDITIONS = ["Новый, в упаковке", "Отличное состояние", "Хорошее состояние, есть следы использования",
              "Состояние среднее, полностью рабочий", "После профилактики"]
EXTRAS = ["Полный комплект, есть коробка и документы.", "Есть чек, гарантия до конца года.",
          "В комплекте чехол и зарядное устройство.", "Без коробки, только сам товар.",
          "Подробные фото отправлю по запросу."]
SEARCH_WORDS = ["смартфон", "часы", "гитара", "ноутбук", "монета", "велосипед", "наушники", "картина", "палатка",
                "Samsung", "Canon", "Yamaha"]


def search_word():
    return random.choice(SEARCH_WORDS)


def lot():
    """Новый лот продавца: название, описание и цены соответствуют категории."""
    category_id, (kind, models, low, high) = random.choice(list(GOODS.items()))
    price = round(random.randint(low, high), -2)
    return {
        "category_id": category_id,
        "title": f"{kind} {random.choice(models)}",
        "description": (f"{random.choice(CONDITIONS)}. {random.choice(EXTRAS)} Куплен в {fake.year()} году. "
                        f"Самовывоз: {fake.city_name()}, возможна отправка почтой."),
        "start_price": price,
        "bid_step": max(100, round(price * random.choice([0.01, 0.02, 0.05]), -2)),
        "submit": random.random() < 0.5,  # половина лотов сразу уходит на модерацию, остальные - черновики
    }


def _passport():
    digits = fake.passport_number().replace(" ", "")
    return f"{digits[:4]} {digits[4:]}"


def _phone():
    return "+79" + fake.numerify("#########")


def person(role):
    """Новый пользователь: ФИО одного пола, совершеннолетний, уникальные логин и e-mail."""
    male = random.random() < 0.5
    login = f"{fake.user_name()}_{uuid.uuid4().hex[:6]}"[:50]
    return {
        "login": login,
        "email": f"{login}@{fake.free_email_domain()}",
        "password": fake.password(length=12, special_chars=False, digits=True, upper_case=True, lower_case=True),
        "role": role,
        "last_name": fake.last_name_male() if male else fake.last_name_female(),
        "first_name": fake.first_name_male() if male else fake.first_name_female(),
        "middle_name": fake.middle_name_male() if male else fake.middle_name_female(),
        "phone": _phone(),
        "birth_date": fake.date_of_birth(minimum_age=18, maximum_age=70).isoformat(),
        "passport": _passport(),
        "address": fake.address(),
    }


def profile(user):
    """Изменение профиля: те же ФИО, новые телефон и адрес (как будто человек переехал)."""
    return {key: user[key] for key in ("last_name", "first_name", "middle_name", "passport")} | {
        "phone": _phone(),
        "address": fake.address(),
    }
