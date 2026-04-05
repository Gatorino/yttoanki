import base64
import streamlit as st
import openai
from openai import OpenAI
import genanki
from youtube_transcript_api import YouTubeTranscriptApi
import pandas as pd
import re
import os

password_input = st.sidebar.text_input("Enter Access Code", type="password")

if password_input != st.secrets["MY_PASSWORD"]:
    st.warning("Please enter the correct access code to use the AI Generator.")
    st.stop()  # This stops the rest of the app from running

# Access the key using dictionary notation
openai_api_key = st.secrets["OPENAI_API_KEY"]

# Example usage with the OpenAI library
client = OpenAI(api_key=openai_api_key)


def extract_video_id(url):
    pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None


def get_youtube_transcript(video_id):
    cookie_path = "temp_cookies.json"
    try:
        if "COOKIE_DATA" in st.secrets:
            cookie_bytes = base64.b64decode(st.secrets["COOKIE_DATA"])
            with open(cookie_path, "wb") as f:
                f.write(cookie_bytes)
        # 1. Create the API instance
        transcript_list = YouTubeTranscriptApi.list_transcripts(
            video_id, cookies=cookie_path)

        # Find and fetch the transcript object
        transcript_obj = transcript_list.find_transcript(['en', 'fr']).fetch()

        # IMPORTANT: .fetch() returns a list of DICTIONARIES, not objects
        # Use snippet['text'], NOT snippet.text
        full_text = " ".join([snippet['text'] for snippet in transcript_obj])

        return full_text
    except Exception as e:
        # Friendly tip for your personal use
        st.error(f"Transcript Error: {e}")
        st.info(
            "Tip: If you're on Streamlit Cloud, make sure your cookies.json is valid and NOT expired.")
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
st.set_page_config(page_title="AI Flashcard Generator",
                   page_icon="🎴", layout="centered")
st.title("🎴 YouTube to Comprehensive Anki Decks")
st.markdown(
    "Use this app on mobile with portrait mode for the easiest experience. Paste your YouTube URL, pick relevant topics, and download the Anki deck directly to your device."
)

with st.form("video_form"):
    url = st.text_input(
        "Paste YouTube URL here:",
        placeholder="https://www.youtube.com/watch?v=...",
        help="A valid YouTube video URL is required to extract the transcript."
    )
    st.form_submit_button("Analyze Video")

if url:
    video_id = extract_video_id(url)

    if video_id:
        if "transcript" not in st.session_state or st.session_state.get('last_id') != video_id:
            with st.spinner("Analyzing video content..."):
                text = get_youtube_transcript(video_id)
                if text:
                    st.session_state.transcript = text
                    st.session_state.topics = get_topics(text)
                    st.session_state.last_id = video_id

        if "topics" in st.session_state:
            st.subheader("Choose your topics")
            selected_topics = st.multiselect(
                "Select one or more topics to include in your deck:",
                options=st.session_state.topics,
                default=[]
            )

            if st.button("Generate Detailed Flashcards"):
                if not selected_topics:
                    st.warning("Please select at least one topic.")
                else:
                    all_cards = []
                    progress_bar = st.progress(0)

                    for i, topic in enumerate(selected_topics):
                        with st.spinner(f"Generating cards for: {topic}..."):
                            topic_cards = generate_flashcards(
                                st.session_state.transcript, topic)
                            all_cards.extend(topic_cards)
                        progress_bar.progress((i + 1) / len(selected_topics))

                    if all_cards:
                        st.success(f"Generated {len(all_cards)} flashcards!")
                        st.markdown(
                            "### Preview your flashcards\nTap the expander below to review a sample before downloading."
                        )
                        with st.expander("Preview Flashcards"):
                            df = pd.DataFrame(all_cards, columns=[
                                              'Question', 'Answer'])
                            st.dataframe(df, use_container_width=True)

                        deck_name = "Combined_YT_Deck" if len(
                            selected_topics) > 1 else selected_topics[0]
                        deck_file = create_anki_deck(all_cards, deck_name)

                        with open(deck_file, "rb") as f:
                            st.download_button(
                                label="💾 Download Anki Deck",
                                data=f,
                                file_name=deck_file,
                                mime="application/octet-stream"
                            )
                    else:
                        st.error(
                            "The AI didn't return any cards. Try different topics.")
