import pyodbc

conn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=IDImport-Cleanup;Trusted_Connection=yes;')
rows = conn.execute("""
SELECT TOP 20 o.name, o.type_desc
FROM sys.objects o
JOIN sys.schemas s ON o.schema_id = s.schema_id
WHERE o.is_ms_shipped = 0
  AND s.name NOT IN ('sys', 'INFORMATION_SCHEMA')
ORDER BY o.name
""").fetchall()
for row in rows:
    print(row[0], row[1])
conn.close()
