import pymongo
import random
import string
from datetime import datetime, timedelta
import re

# Connect to MongoDB
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["syn"]
collection = db["syn4"]

# Define the schema
schema = {
    "date_field": "date",
    "id_field_1": "regex_1",
    "id_field_2": "regex_2",
    "currency_field": "currency",
    "value_field": "decimal",
}

# Define regex patterns
regex_patterns = {
    "regex_1": r"^[0-9A-Z]{6}|[0-9A-Z]{12}$",
    "regex_2": r"^[0-9A-Z]{1,16}$",
    "regex_3": r"^[0-9A-Z]{1,35}$",
}


# Function to generate random date between 2020 and 2023
def generate_random_date(start_year=2020, end_year=2023):
    start_date = datetime(start_year, 1, 1)
    end_date = datetime(end_year, 12, 31)
    delta = end_date - start_date
    random_days = random.randint(0, delta.days)
    return start_date + timedelta(days=random_days)


# Function to generate random string based on regex pattern
def generate_random_string(pattern):
    while True:
        generated_string = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=35)
        )
        if re.match(pattern, generated_string):
            return generated_string


# Function to generate random currency
def generate_random_currency():
    return random.choice(["EUR", "GBP", "USD"])


# Function to generate random decimal value
def generate_random_decimal():
    return round(random.uniform(1, 1000), 2)


# Generate synthetic data
def generate_synthetic_data(num_records):
    data = []
    for _ in range(num_records):
        record = {
            "date_field": generate_random_date(),
            "id_field_1": generate_random_string(regex_patterns["regex_1"]),
            "id_field_2": generate_random_string(regex_patterns["regex_2"]),
            "currency_field": generate_random_currency(),
            "value_field": generate_random_decimal(),
        }
        data.append(record)
    return data


# Insert synthetic data into MongoDB
def insert_data_into_mongodb(data):
    collection.insert_many(data)
    print(f"Inserted {len(data)} records into MongoDB")


# Generate and insert data
num_records = 1000
synthetic_data = generate_synthetic_data(num_records)
insert_data_into_mongodb(synthetic_data)

print("Data generation and insertion complete.")
