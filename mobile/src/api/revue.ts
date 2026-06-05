export type RevueUser = {
  id: number;
  username: string;
  name: string;
  profile_photo: string;
  profile_url: string;
};

export type RevueItem = {
  id: number;
  title: string;
  item_type: string;
  item_type_label: string;
  release_year: string;
  creator_name: string;
  cast_names: string;
  description: string;
  image_url: string;
  imdb_rating: string;
  rt_rating: string;
  book_rating: string;
  likes: number;
  saves: number;
  url: string;
};

export type FeedReview = {
  id: number;
  rating: number;
  review_text: string;
  created_at: string;
  user: RevueUser;
  item: RevueItem;
  counts: {
    review_likes: number;
    comments: number;
    item_likes: number;
  };
  url: string;
};

export type DiscoverItem = {
  title: string;
  item_type: string;
  year: string;
  creator: string;
  description: string;
  image_url: string;
  url: string;
};

export type DiscoverSection = {
  title: string;
  kicker: string;
  items: DiscoverItem[];
};

declare const process: {
  env: {
    EXPO_PUBLIC_REVUE_API_URL?: string;
  };
};

const API_BASE_URL = process.env.EXPO_PUBLIC_REVUE_API_URL || "https://www.revue.social";

const fallbackReviews: FeedReview[] = [
  {
    id: 1,
    rating: 5,
    review_text: "A sharp, social way to remember what is actually worth watching next.",
    created_at: new Date().toISOString(),
    user: {
      id: 1,
      username: "revue",
      name: "Revue",
      profile_photo: "",
      profile_url: `${API_BASE_URL}/users/revue/`
    },
    item: {
      id: 1,
      title: "Your next recommendation",
      item_type: "series",
      item_type_label: "Series",
      release_year: "2026",
      creator_name: "People you trust",
      cast_names: "",
      description: "",
      image_url: "",
      imdb_rating: "",
      rt_rating: "",
      book_rating: "",
      likes: 0,
      saves: 0,
      url: API_BASE_URL
    },
    counts: {
      review_likes: 0,
      comments: 0,
      item_likes: 0
    },
    url: API_BASE_URL
  }
];

export async function fetchFeed(): Promise<FeedReview[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/feed/?limit=20`);
    if (!response.ok) {
      throw new Error(`Revue API returned ${response.status}`);
    }
    const payload = (await response.json()) as { results?: FeedReview[] };
    return payload.results?.length ? payload.results : fallbackReviews;
  } catch {
    return fallbackReviews;
  }
}

export async function fetchDiscover(section: "media" | "books" = "media"): Promise<DiscoverSection[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/discover/?section=${section}`);
    if (!response.ok) {
      throw new Error(`Revue API returned ${response.status}`);
    }
    const payload = (await response.json()) as { sections?: DiscoverSection[] };
    return payload.sections?.length ? payload.sections : fallbackDiscoverSections(section);
  } catch {
    return fallbackDiscoverSections(section);
  }
}

function fallbackDiscoverSections(section: "media" | "books"): DiscoverSection[] {
  if (section === "books") {
    return [
      {
        title: "Books people keep recommending",
        kicker: "Reliable starts for your reading list",
        items: [
          {
            title: "Atomic Habits",
            item_type: "book",
            year: "2018",
            creator: "James Clear",
            description: "A practical guide to better habits.",
            image_url: "https://covers.openlibrary.org/b/isbn/9780735211292-L.jpg",
            url: API_BASE_URL
          },
          {
            title: "The Midnight Library",
            item_type: "book",
            year: "2020",
            creator: "Matt Haig",
            description: "A warm novel about possible lives.",
            image_url: "https://covers.openlibrary.org/b/isbn/9780525559474-L.jpg",
            url: API_BASE_URL
          }
        ]
      }
    ];
  }
  return [
    {
      title: "Talk of the town",
      kicker: "Movies and series to open next",
      items: [
        {
          title: "Succession",
          item_type: "series",
          year: "2018",
          creator: "Jesse Armstrong",
          description: "Power, family, and ambition.",
          image_url: "",
          url: API_BASE_URL
        },
        {
          title: "The Social Network",
          item_type: "movie",
          year: "2010",
          creator: "David Fincher",
          description: "A sharp founder story.",
          image_url: "",
          url: API_BASE_URL
        }
      ]
    }
  ];
}
