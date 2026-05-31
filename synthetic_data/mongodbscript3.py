from pymongo import MongoClient
import random
import string
from datetime import datetime, timedelta, timezone

def generate_random_datetime(start_date, end_date):
    # Generates a random datetime between start_date and end_date
    time_between_dates = end_date - start_date
    random_days = random.randrange(time_between_dates.days)
    random_seconds = random.randint(0, 86399)  # seconds in a day
    random_date = start_date + timedelta(days=random_days, seconds=random_seconds)
    return random_date

def reset_database():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['testdb']
    db.orders.drop()
    
    start_date = datetime(2022, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2023, 12, 31, tzinfo=timezone.utc)

    for i in range(1000000):
        random_datetime = generate_random_datetime(start_date, end_date)
        random_date = datetime(random_datetime.year, random_datetime.month, random_datetime.day, tzinfo=timezone.utc)  # Just the date part, timezone-aware
        
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
            "date": random_date,  # Only the date part
            "date_time": random_datetime  # Date and time part
        }
        db.orders.insert_one(document)


        
def generate_name():
    first_names = ["John", "Jane", "Corey", "Mia", "Chris", "Angela", "Max", "Lily", "James", "Patricia"]
    last_names = ["Doe", "Smith", "Johnson", "Turner", "Lewis", "Walker", "Brown", "White", "Harris", "Martin"]
    return random.choice(first_names) + " " + random.choice(last_names)

def generate_string(n):
    ran = ''.join(random.choices(string.ascii_letters + string.digits, k = n))
    return str(ran)   

def generate_city():
    cities = ["New York", "Los Angeles", "Chicago", "Houston", "Seattle"]
    return random.choice(cities)

reset_database()
