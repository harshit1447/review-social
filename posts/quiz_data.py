from datetime import date
import random


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
    {
        "question": "Which movie features Neo choosing between a red pill and a blue pill?",
        "options": ["The Matrix", "Minority Report", "Blade Runner"],
        "answer": "The Matrix",
    },
    {
        "question": "Which series is about a chemistry teacher turning into a meth producer?",
        "options": ["Breaking Bad", "Ozark", "Narcos"],
        "answer": "Breaking Bad",
    },
    {
        "question": "Who directed The Social Network?",
        "options": ["David Fincher", "Aaron Sorkin", "Danny Boyle"],
        "answer": "David Fincher",
    },
    {
        "question": "Which movie follows a jazz drummer named Andrew Neiman?",
        "options": ["Whiplash", "La La Land", "Birdman"],
        "answer": "Whiplash",
    },
    {
        "question": "Which series features the characters Ross, Rachel, Monica, Chandler, Joey, and Phoebe?",
        "options": ["Friends", "How I Met Your Mother", "Seinfeld"],
        "answer": "Friends",
    },
    {
        "question": "Which movie is set on the desert planet Arrakis?",
        "options": ["Dune", "Avatar", "Interstellar"],
        "answer": "Dune",
    },
    {
        "question": "Which series follows Sherlock Holmes and Dr. John Watson in modern London?",
        "options": ["Sherlock", "Luther", "Broadchurch"],
        "answer": "Sherlock",
    },
    {
        "question": "Which film has the quote, 'Why so serious?'",
        "options": ["The Dark Knight", "Joker", "Batman Begins"],
        "answer": "The Dark Knight",
    },
    {
        "question": "Which movie follows a group entering dreams within dreams?",
        "options": ["Inception", "Tenet", "Memento"],
        "answer": "Inception",
    },
    {
        "question": "Which series is centered on the Dunder Mifflin paper company?",
        "options": ["The Office", "Parks and Recreation", "30 Rock"],
        "answer": "The Office",
    },
    {
        "question": "Which film won Best Picture at the 2020 Oscars?",
        "options": ["Parasite", "1917", "Once Upon a Time in Hollywood"],
        "answer": "Parasite",
    },
    {
        "question": "Which series follows a football coach managing AFC Richmond?",
        "options": ["Ted Lasso", "The Bear", "Friday Night Lights"],
        "answer": "Ted Lasso",
    },
    {
        "question": "Which movie has the character Tyler Durden?",
        "options": ["Fight Club", "American Psycho", "The Departed"],
        "answer": "Fight Club",
    },
    {
        "question": "Which series takes place in the fictional continent of Westeros?",
        "options": ["Game of Thrones", "The Witcher", "Vikings"],
        "answer": "Game of Thrones",
    },
    {
        "question": "Which film follows Mark Watney stranded on Mars?",
        "options": ["The Martian", "Gravity", "Ad Astra"],
        "answer": "The Martian",
    },
    {
        "question": "Which series follows Carmy rebuilding a Chicago sandwich shop?",
        "options": ["The Bear", "Chef's Table", "Shameless"],
        "answer": "The Bear",
    },
    {
        "question": "Which movie features the fictional hotel The Overlook?",
        "options": ["The Shining", "Psycho", "Get Out"],
        "answer": "The Shining",
    },
    {
        "question": "Which series follows the staff of a fictional White House administration?",
        "options": ["The West Wing", "House of Cards", "Veep"],
        "answer": "The West Wing",
    },
    {
        "question": "Which movie stars Tom Hanks as Forrest Gump?",
        "options": ["Forrest Gump", "Cast Away", "Big"],
        "answer": "Forrest Gump",
    },
    {
        "question": "Which series is about an alternate office where workers split work and personal memories?",
        "options": ["Severance", "Black Mirror", "Devs"],
        "answer": "Severance",
    },
    {
        "question": "Which movie follows a drummer, a singer, and a city called Los Angeles in a musical romance?",
        "options": ["La La Land", "A Star Is Born", "Moulin Rouge!"],
        "answer": "La La Land",
    },
    {
        "question": "Which series follows a group surviving in a post-apocalyptic world with infected creatures?",
        "options": ["The Last of Us", "The Walking Dead", "Lost"],
        "answer": "The Last of Us",
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
    {
        "question": "Which film follows Mahavir Singh Phogat training his daughters in wrestling?",
        "options": ["Dangal", "Sultan", "Mary Kom"],
        "answer": "Dangal",
    },
    {
        "question": "Who directed Dil Chahta Hai?",
        "options": ["Farhan Akhtar", "Karan Johar", "Imtiaz Ali"],
        "answer": "Farhan Akhtar",
    },
    {
        "question": "Which film features the character Geet played by Kareena Kapoor?",
        "options": ["Jab We Met", "Kabhi Khushi Kabhie Gham", "Chameli"],
        "answer": "Jab We Met",
    },
    {
        "question": "Which movie stars Shah Rukh Khan as Kabir Khan?",
        "options": ["Chak De! India", "Swades", "My Name Is Khan"],
        "answer": "Chak De! India",
    },
    {
        "question": "Which film follows a pregnant woman searching for her missing husband in Kolkata?",
        "options": ["Kahaani", "Talaash", "Raazi"],
        "answer": "Kahaani",
    },
    {
        "question": "Which movie is about a deaf and mute man played by Ranbir Kapoor?",
        "options": ["Barfi!", "Rockstar", "Tamasha"],
        "answer": "Barfi!",
    },
    {
        "question": "Who directed Gully Boy?",
        "options": ["Zoya Akhtar", "Meghna Gulzar", "Anurag Kashyap"],
        "answer": "Zoya Akhtar",
    },
    {
        "question": "Which film features the song 'Chaiyya Chaiyya'?",
        "options": ["Dil Se..", "Bombay", "Roja"],
        "answer": "Dil Se..",
    },
    {
        "question": "Which movie follows a man returning to India to help his village?",
        "options": ["Swades", "Lagaan", "Rang De Basanti"],
        "answer": "Swades",
    },
    {
        "question": "Which film is centered around a blind pianist and a murder?",
        "options": ["Andhadhun", "Badlapur", "Drishyam"],
        "answer": "Andhadhun",
    },
    {
        "question": "Which movie features the characters Munna and Circuit?",
        "options": ["Munna Bhai M.B.B.S.", "Hera Pheri", "Golmaal"],
        "answer": "Munna Bhai M.B.B.S.",
    },
    {
        "question": "Who directed Queen?",
        "options": ["Vikas Bahl", "Anurag Basu", "Shoojit Sircar"],
        "answer": "Vikas Bahl",
    },
    {
        "question": "Which film follows a RAW agent named Sehmat?",
        "options": ["Raazi", "Ek Tha Tiger", "Baby"],
        "answer": "Raazi",
    },
    {
        "question": "Which movie has the characters Raju, Shyam, and Baburao?",
        "options": ["Hera Pheri", "Welcome", "Bhool Bhulaiyaa"],
        "answer": "Hera Pheri",
    },
    {
        "question": "Which film follows Milkha Singh's life?",
        "options": ["Bhaag Milkha Bhaag", "Gold", "Soorma"],
        "answer": "Bhaag Milkha Bhaag",
    },
    {
        "question": "Which movie stars Amitabh Bachchan as a lawyer named Deepak Sehgal?",
        "options": ["Pink", "Badla", "Piku"],
        "answer": "Pink",
    },
    {
        "question": "Which film follows a young girl trying to become a singer while hiding her identity?",
        "options": ["Secret Superstar", "English Vinglish", "Dear Zindagi"],
        "answer": "Secret Superstar",
    },
    {
        "question": "Who directed Piku?",
        "options": ["Shoojit Sircar", "Imtiaz Ali", "Sanjay Leela Bhansali"],
        "answer": "Shoojit Sircar",
    },
    {
        "question": "Which movie follows a mathematics genius from Patna preparing students for IIT?",
        "options": ["Super 30", "Hichki", "Nil Battey Sannata"],
        "answer": "Super 30",
    },
    {
        "question": "Which film features the character Ved and explores storytelling and identity?",
        "options": ["Tamasha", "Rockstar", "Wake Up Sid"],
        "answer": "Tamasha",
    },
    {
        "question": "Which movie follows a middle-class family and an unexpected pregnancy?",
        "options": ["Badhaai Ho", "Shubh Mangal Saavdhan", "Bareilly Ki Barfi"],
        "answer": "Badhaai Ho",
    },
    {
        "question": "Which film is about India's 1983 Cricket World Cup win?",
        "options": ["83", "M.S. Dhoni: The Untold Story", "Jersey"],
        "answer": "83",
    },
]


def _daily_pick(question_bank, current_date, count, salt):
    cycle_days = max(1, len(question_bank) // count)
    day_index = current_date.toordinal()
    cycle_index = day_index // cycle_days
    position = day_index % cycle_days
    indices = list(range(len(question_bank)))
    random.Random(f"revue-quiz:{salt}:{cycle_index}").shuffle(indices)
    start = position * count
    picked_indices = indices[start : start + count]
    if len(picked_indices) < count:
        picked_indices += indices[: count - len(picked_indices)]
    return [question_bank[index] for index in picked_indices]


def get_daily_quiz(current_date=None):
    current_date = current_date or date.today()
    questions = []
    for section, question in (
        [("Hollywood", row) for row in _daily_pick(HOLLYWOOD_QUESTIONS, current_date, 3, "hollywood")]
        + [("Bollywood", row) for row in _daily_pick(BOLLYWOOD_QUESTIONS, current_date, 3, "bollywood")]
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
