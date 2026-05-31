from pymongo import MongoClient
import random
import string
from datetime import datetime, timedelta
import re

def reset_database():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['mydb']
    db.orders.drop()

    for i in range(10000000):
        id_field_1 = generate_fixed_length_string(12)  # Always 12 characters
        id_field_2 = generate_variable_length_string(1, 16)  # Length between 1 and 16
        
        document = {
            "i": i,
            "name": generate_name(),
            "age": random.randint(0, 100),
            "fav": random.randint(0, 100000),
            "number": random.randint(1, 5),
            "city": generate_city(),
            "order_amount": round(random.uniform(0, 100000.0), 2),
            "balance": round(random.uniform(0.00, 100000.00), 10),
            "string": generate_string(16),
            "text": "Enim nec dui nunc mattis enim ut. Aliquet nibh praesent tristique magna. Hac habitasse platea dictumst vestibulum rhoncus est. Amet cursus sit amet dictum sit amet justo. Et tortor consequat id porta nibh venenatis cras sed felis. Vel risus commodo viverra maecenas accumsan lacus vel facilisis. Pretium fusce id velit ut tortor pretium viverra suspendisse potenti. Lectus magna fringilla urna porttitor rhoncus dolor purus. Duis tristique sollicitudin nibh sit. Ac feugiat sed lectus vestibulum mattis ullamcorper velit. Sagittis id consectetur purus ut. Tristique senectus et netus et. Eu consequat ac felis donec. Posuere sollicitudin aliquam ultrices sagittis orci.",
            "date_field": generate_random_date(),
            "id_field_1": id_field_1,
            "id_field_2": id_field_2,
            "currency_field": generate_random_currency(),
            "value_field": generate_random_decimal()
        }
        db.orders.insert_one(document)


def generate_fixed_length_string(length):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def generate_variable_length_string(min_length, max_length):
    length = random.randint(min_length, max_length)
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def generate_string(n):
    ran = ''.join(random.choices(string.ascii_letters + string.digits, k=n))
    return str(ran)   


def generate_name():
    first_names = ["John", "Jane", "Corey", "Mia", "Chris", "Angela", "Max", "Lily", "James", "Patricia"]
    last_names = ["Doe", "Smith", "Johnson", "Turner", "Lewis", "Walker", "Brown", "White", "Harris", "Martin"]
    return random.choice(first_names) + " " + random.choice(last_names)



def generate_city():
    cities = ["New York", "Los Angeles", "Chicago", "Houston", "Seattle"]
    return random.choice(cities)

def generate_random_date(start_year=2020, end_year=2023):
    start_date = datetime(start_year, 1, 1)
    end_date = datetime(end_year, 12, 31)
    delta = end_date - start_date
    random_days = random.randint(0, delta.days)
    return start_date + timedelta(days=random_days)

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def generate_random_string(pattern, max_length):
    pattern_compiled = re.compile(pattern)
    for _ in range(1000):  # Limit the number of attempts to avoid an infinite loop
        generated_string = ''.join(random.choices(string.ascii_uppercase + string.digits, k=random.randint(1, max_length)))
        if pattern_compiled.fullmatch(generated_string):
            return generated_string
    logging.warning(f"No valid string generated for pattern: {pattern}")
    return None  # Return None if no valid string is generated


def generate_random_currency():
    return random.choice(["EUR", "GBP", "USD"])

def generate_random_decimal():
    return round(random.uniform(1, 1000), 2)

reset_database()