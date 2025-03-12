import os
import requests
from bs4 import BeautifulSoup
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import pickle

BASE_URL = "https://medlineplus.gov/ency/"

def fetch_page(url):
    response = requests.get(url)
    return response.text if response.status_code == 200 else None

def extract_text(html):
    soup = BeautifulSoup(html, "html.parser")
    
    # Extract article title
    title_tag = soup.find("h1", class_="with-also", itemprop="name")
    article_title = title_tag.get_text(strip=True) if title_tag else "Untitled"
    safe_title = "".join(c for c in article_title if c.isalnum() or c in " _-").strip()

    extracted_text = [f"Title: {safe_title}"]

    for section in soup.find_all("div", class_="section"):
        title_div = section.find("div", class_="section-title")
        body_div = section.find("div", class_="section-body")

        if title_div and body_div:
            section_title = title_div.get_text(strip=True)
            section_content = body_div.get_text(" ", strip=True)
            
            if any(exclude in section_title.lower() for exclude in ["images", "references", "review date"]):
                continue

            extracted_text.append(f"\n{section_title}\n{section_content}")

    return safe_title, "\n".join(extracted_text)

def save_to_file(alphabet, title, content):
    folder_path = os.path.join("articles", alphabet)
    os.makedirs(folder_path, exist_ok=True)
    file_path = os.path.join(folder_path, f"{title}.txt")

    with open(file_path, "w", encoding="utf-8") as file:
        file.write(content)

    print(f"Saved: {file_path}")

def get_article_links(alphabet):
    url = f"{BASE_URL}encyclopedia_{alphabet}.htm"
    html = fetch_page(url)
    
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    article_links = []

    for li in soup.select("#mplus-content li"):
        if not li.get("class"):
            a_tag = li.find("a", href=True)
            if a_tag and a_tag["href"].startswith("article/"):
                article_links.append(BASE_URL + a_tag["href"])

    return article_links

def scrape_alphabets(alphabets):
    for alphabet in alphabets:
        print(f"\nProcessing articles for: {alphabet}")
        article_links = get_article_links(alphabet)

        for link in article_links:
            print(f"Extracting from: {link}")
            html = fetch_page(link)

            if html:
                title, extracted_text = extract_text(html)
                save_to_file(alphabet, title, extracted_text)

def combine_articles():
    """Combines all text from scraped articles into one large text file."""
    combined_text = ""

    for alpha in os.listdir("articles"):
        folder_path = os.path.join("articles", alpha)
        if os.path.isdir(folder_path):
            for file_name in sorted(os.listdir(folder_path)):  # Ensure alphabetical order
                file_path = os.path.join(folder_path, file_name)
                with open(file_path, "r", encoding="utf-8") as file:
                    combined_text += file.read() + "\n\n"

    return combined_text

def chunk_text(text, max_tokens=200):
    """Splits text into chunks based on max token limit."""
    words = text.split()
    return [" ".join(words[i:i + max_tokens]) for i in range(0, len(words), max_tokens)]

def create_embeddings(text, model_name="all-MiniLM-L6-v2"):
    """Generates embeddings for the combined text chunks."""
    model = SentenceTransformer(model_name)
    chunks = chunk_text(text)

    print(f"Total chunks: {len(chunks)}")

    embeddings = model.encode(chunks, show_progress_bar=True)
    return embeddings, chunks

def store_in_vector_db(embeddings, chunks, index_path="medical_index.faiss", metadata_path="metadata.pickle"):
    """Stores embeddings and corresponding text in FAISS."""
    embeddings = np.array(embeddings).astype('float32')
    dimension = embeddings.shape[1]

    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)

    faiss.write_index(index, index_path)

    with open(metadata_path, 'wb') as f:
        pickle.dump(chunks, f)

    print("Embeddings stored successfully!")

def input_alphabet():
    """Prompts the user to input an alphabet for scraping."""
    alphabet = input("Enter the alphabet to scrape (e.g., A, B, C): ").strip().upper()
    return alphabet

def medical_query_input(query, index_path="medical_index.faiss", metadata_path="metadata.pickle"):
    """Processes a medical query and retrieves relevant articles."""
    # Load the FAISS index and metadata
    index = faiss.read_index(index_path)
    with open(metadata_path, 'rb') as f:
        chunks = pickle.load(f)

    # Create embeddings for the query
    model = SentenceTransformer("all-MiniLM-L6-v2")
    query_embedding = model.encode([query])

    # Search for the nearest neighbors
    D, I = index.search(np.array(query_embedding).astype('float32'), k=5)  # Get top 5 results

    # Display the results
    print("\nTop relevant articles for your query:")
    for i in range(len(I[0])):
        if I[0][i] != -1:  # Check if the index is valid
            print(f"{i + 1}. {chunks[I[0][i]]} (Distance: {D[0][i]})")

if __name__ == "__main__":
    # Get user input for alphabet
    alphabet_to_scrape = input_alphabet()
    scrape_alphabets([alphabet_to_scrape])

    print("\nCombining articles...")
    combined_text = combine_articles()

    print("\nGenerating embeddings...")
    embeddings, chunks = create_embeddings(combined_text)

    print("\nStoring in FAISS...")
    store_in_vector_db(embeddings, chunks)

    # Get user input for medical query
    medical_query = input("Enter a medical query to search for relevant articles: ")
    medical_query_input(medical_query)