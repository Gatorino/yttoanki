import streamlit as st
import openai
from openai import OpenAI
import genanki
from youtube_transcript_api import YouTubeTranscriptApi
import pandas as pd
import re
import os

# Access the key using dictionary notation
openai_api_key = st.secrets["OPENAI_API_KEY"]

# Example usage with the OpenAI library
client = OpenAI(api_key=openai_api_key)


def extract_video_id(url):
    pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None


def get_youtube_transcript(video_id):
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)

        # This returns a "FetchedTranscript" object
        transcript_obj = transcript_list.find_transcript(['en', 'fr']).fetch()

        # Access .text as an attribute, not a dictionary key
        full_text = " ".join([snippet.text for snippet in transcript_obj])
        return full_text

    except Exception as e:
        st.error(f"Could not retrieve transcript. Error: {e}")
        return None


def get_topics(text):
    """Asks the LLM to find all relevant topics without a fixed limit."""
    response = openai.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[{"role": "user", "content": f"Identify all the distinct, major educational topics covered in this video transcript. Return them as a simple comma-separated list. Transcript: {text[:8000]}"}]
    )
    return [t.strip() for t in response.choices[0].message.content.split(",")]


def generate_flashcards(text, topic):
    """Asks the LLM to create a comprehensive list of cards for the chosen topic."""
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"Based on the following transcript, create a comprehensive set of Anki flashcards for the topic: '{topic}'. Create as many cards as necessary to cover the material thoroughly using Active Recall principles. Format: Question | Answer. One per line. Transcript: {text[:10000]}"}]
    )
    lines = response.choices[0].message.content.strip().split('\n')
    cards = [line.split('|') for line in lines if '|' in line]
    return cards


def create_anki_deck(cards, deck_name):
    # Unique IDs for the model and deck
    model_id = 1607392319
    deck_id = 2059400110

    model = genanki.Model(
        model_id, 'Simple Model',
        fields=[{'name': 'Question'}, {'name': 'Answer'}],
        templates=[{'name': 'Card 1', 'qfmt': '{{Question}}',
                    'afmt': '{{FrontSide}}<hr id="answer">{{Answer}}'}]
    )
    deck = genanki.Deck(deck_id, deck_name)

    for card in cards:
        if len(card) == 2:
            deck.add_note(genanki.Note(model=model, fields=[
                          card[0].strip(), card[1].strip()]))

    output_file = f"{deck_name.replace(' ', '_')}.apkg"
    genanki.Package(deck).write_to_file(output_file)
    return output_file


# --- STREAMLIT UI ---
st.set_page_config(page_title="AI Flashcard Generator", page_icon="🎴")
st.title("🎴 YouTube to Comprehensive Anki Decks")

url = st.text_input("Paste YouTube URL here:")

if url:
    video_id = extract_video_id(url)

    if video_id:
        # Cache the transcript so it doesn't reload on every click
        if "transcript" not in st.session_state or st.session_state.get('last_id') != video_id:
            with st.spinner("Analyzing video content..."):
                text = get_youtube_transcript(video_id)
                if text:
                    st.session_state.transcript = text
                    st.session_state.topics = get_topics(text)
                    st.session_state.last_id = video_id

        if "topics" in st.session_state:
            st.subheader("Choose a topic to master:")
            selected_topic = st.selectbox(
                "Relevant Topics Found:", st.session_state.topics)

            if st.button("Generate Detailed Flashcards"):
                with st.spinner(f"Generating comprehensive cards for {selected_topic}..."):
                    cards = generate_flashcards(
                        st.session_state.transcript, selected_topic)

                    if cards:
                        st.success(f"Generated {len(cards)} flashcards!")
                        df = pd.DataFrame(
                            cards, columns=['Question', 'Answer'])
                        st.dataframe(df, use_container_width=True)

                        deck_file = create_anki_deck(cards, selected_topic)

                        with open(deck_file, "rb") as f:
                            st.download_button(
                                label="💾 Download Anki Deck",
                                data=f,
                                file_name=deck_file,
                                mime="application/octet-stream"
                            )
                    else:
                        st.error(
                            "The AI didn't return any cards. Try a different topic.")
