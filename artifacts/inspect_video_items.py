import json
import sqlite3

con = sqlite3.connect("db.sqlite3")
con.row_factory = sqlite3.Row
cols = [row[1] for row in con.execute("pragma table_info(posts_item)").fetchall()]
print("columns:", cols)
select_cols = [c for c in ["id", "title", "item_type", "release_year", "image_url", "imdb_rating", "book_rating"] if c in cols]
rows = con.execute(
    f"""
    select {", ".join(select_cols)}
    from posts_item
    where length(coalesce(image_url, '')) > 0
    order by id desc
    limit 40
    """
).fetchall()
print(json.dumps([dict(row) for row in rows], indent=2))
