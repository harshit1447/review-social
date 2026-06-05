from datetime import date


HOLLYWOOD_QUESTIONS = [
    {
        "question": "Which movie features the line, 'I'm the king of the world'?",
        "options": ["Titanic", "Top Gun", "The Matrix"],
        "answer": "Titanic",
    },
    {
        "question": "Who directed Inception?",
        "options": ["Christopher Nolan", "David Fincher", "Steven Spielberg"],
        "answer": "Christopher Nolan",
    },
    {
        "question": "Which series is set mainly in Hawkins, Indiana?",
        "options": ["Stranger Things", "Dark", "The Boys"],
        "answer": "Stranger Things",
    },
    {
        "question": "Which movie follows Andy Dufresne in prison?",
        "options": ["The Shawshank Redemption", "Fight Club", "Se7en"],
        "answer": "The Shawshank Redemption",
    },
    {
        "question": "Which series follows the Roy family and Waystar Royco?",
        "options": ["Succession", "Mad Men", "Billions"],
        "answer": "Succession",
    },
    {
        "question": "Which film introduced the character Jack Sparrow?",
        "options": ["Pirates of the Caribbean", "The Mummy", "National Treasure"],
        "answer": "Pirates of the Caribbean",
    },
]


BOLLYWOOD_QUESTIONS = [
    {
        "question": "Which film features Rancho, Farhan, and Raju?",
        "options": ["3 Idiots", "Zindagi Na Milegi Dobara", "Dil Chahta Hai"],
        "answer": "3 Idiots",
    },
    {
        "question": "Who directed Lagaan?",
        "options": ["Ashutosh Gowariker", "Rajkumar Hirani", "Farhan Akhtar"],
        "answer": "Ashutosh Gowariker",
    },
    {
        "question": "Which movie is about the Indian women's national hockey team?",
        "options": ["Chak De! India", "Dangal", "Bhaag Milkha Bhaag"],
        "answer": "Chak De! India",
    },
    {
        "question": "Which film stars Aamir Khan as a teacher for a dyslexic child?",
        "options": ["Taare Zameen Par", "Secret Superstar", "PK"],
        "answer": "Taare Zameen Par",
    },
    {
        "question": "Which film is centered around a missing person named Sameer in Goa?",
        "options": ["Drishyam", "Kahaani", "Talaash"],
        "answer": "Drishyam",
    },
    {
        "question": "Which movie follows three friends on a road trip through Spain?",
        "options": ["Zindagi Na Milegi Dobara", "Wake Up Sid", "Rock On!!"],
        "answer": "Zindagi Na Milegi Dobara",
    },
]


def _daily_pick(question_bank, current_date, count):
    start = current_date.toordinal() % len(question_bank)
    return [question_bank[(start + index) % len(question_bank)] for index in range(count)]


def get_daily_quiz(current_date=None):
    current_date = current_date or date.today()
    questions = []
    for section, question in (
        [("Hollywood", row) for row in _daily_pick(HOLLYWOOD_QUESTIONS, current_date, 3)]
        + [("Bollywood", row) for row in _daily_pick(BOLLYWOOD_QUESTIONS, current_date, 3)]
    ):
        questions.append(
            {
                "section": section,
                "question": question["question"],
                "options": question["options"],
                "answer": question["answer"],
            }
        )
    return questions
