import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')

def init_db():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Nut_Details (
            nut_name TEXT PRIMARY KEY,
            daily_serving TEXT,
            max_limit TEXT,
            good_pairing TEXT,
            bad_pairing TEXT,
            recipe_tip TEXT
        )
    ''')

    # Sample data
    sample_data = [
        ('아몬드', '20알 권장', '30알 이상 주의', '요거트와 궁합', '홍차와 비추', '샐러드 토핑 활용'),
        ('호두', '5~7알 권장', '과다 섭취 시 설사 주의', '우유와 궁합', '특별히 나쁜 궁합 없음', '멸치볶음 활용'),
        ('캐슈넛', '10~15알 권장', '고칼로리 주의', '닭고기와 궁합', '산성 음식과 비추', '커리 요리 활용'),
        ('피스타치오', '20~30알 권장', '칼로리 주의 및 알레르기 확인', '포도와 궁합', '특별히 나쁜 궁합 없음', '아이스크림 토핑 및 페스토 활용')
    ]

    # Insert data (use REPLACE to avoid errors on multiple runs)
    cursor.executemany('''
        INSERT OR REPLACE INTO Nut_Details 
        (nut_name, daily_serving, max_limit, good_pairing, bad_pairing, recipe_tip)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', sample_data)

    conn.commit()
    conn.close()
    print(f"Database successfully created and initialized at: {db_path}")

if __name__ == "__main__":
    init_db()
