from database import get_connection


connection = get_connection()
cursor = connection.cursor()

cursor.execute("""
    SELECT TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE = 'BASE TABLE'
    ORDER BY TABLE_NAME
""")

print("Tables in MTGCardScanner:")
print()

for row in cursor.fetchall():
    print(row.TABLE_NAME)

connection.close()