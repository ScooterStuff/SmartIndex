import random
from pymongo import MongoClient

# Function to generate a random name
def generate_name():
    first_names = ["John", "Jane", "Corey", "Mia", "Chris", "Angela", "Max", "Lily", "James", "Patricia"]
    last_names = ["Doe", "Smith", "Johnson", "Turner", "Lewis", "Walker", "Brown", "White", "Harris", "Martin"]
    return random.choice(first_names) + " " + random.choice(last_names)

# Function to generate a random city
def generate_city():
    cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose"]
    return random.choice(cities)

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['mydb']
collection = db['orders']

# Generate and insert 10,000 random documents
for _ in range(10000):
    document = {
        "name": generate_name(),
        "age": random.randint(18, 70),  # Random age between 18 and 70
        "city": generate_city(),
        "order_amount": random.uniform(50.0, 500.0),  # Random order amount between $50 and $500
        "balance":random.uniform(0.00,100000.00)
    }
    collection.insert_one(document)
collection.insert_one({
    "name": "Mia Lewis",
    "age": 49,  # Random age between 18 and 70
    "city": "Pheonix",
    "order_amount": random.uniform(50.0, 500.0),  # Random order amount between $50 and $500
    "balance":random.uniform(0.00,100000.00)
})

# Retrieve all documents
documents = collection.find()

# Print each document
# for doc in documents:
#     print(doc)

query = {"name": {"$regex": "^John"}}
query = {"name": "John Doe"}

# Execute query using a specific index
# Replace 'index_name' with the actual name of your index
with_index = collection.find(query).hint('name_1').explain()

# Execute query without using any index
without_index = collection.find(query).hint({'$natural': 1}).explain()

# Extracting execution time and examining stats
print("With Index:")
print(f"Execution Time (ms): {with_index['executionStats'].get('executionTimeMillis', 'N/A')}")
print(f"Total Keys Examined: {with_index['executionStats'].get('totalKeysExamined', 'N/A')}")
print(f"Total Docs Examined: {with_index['executionStats'].get('totalDocsExamined', 'N/A')}")

print("\nWithout Index:")
print(f"Execution Time (ms): {without_index['executionStats'].get('executionTimeMillis', 'N/A')}")
print(f"Total Keys Examined: {without_index['executionStats'].get('totalKeysExamined', 'N/A')}")
print(f"Total Docs Examined: {without_index['executionStats'].get('totalDocsExamined', 'N/A')}")