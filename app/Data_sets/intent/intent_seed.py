"""Synthetic assistant intent corpus (PRD §8).
Swap with SNIPS/ATIS by loading into the same (text, intent) shape."""

INTENT_DATA: list[tuple[str, str]] = [
    # SCHEDULE_EVENT
    ("schedule a meeting with john tomorrow at 10", "SCHEDULE_EVENT"),
    ("book a meeting with the team next monday at 3", "SCHEDULE_EVENT"),
    ("can you put a meeting with sarah on my calendar friday at 2 pm", "SCHEDULE_EVENT"),
    ("set up a call with rahul tomorrow morning", "SCHEDULE_EVENT"),
    ("add an appointment with the dentist on wednesday at 11", "SCHEDULE_EVENT"),
    ("arrange a sync with product team day after tomorrow at 4", "SCHEDULE_EVENT"),
    ("create a calendar event for the review tomorrow at 9 am", "SCHEDULE_EVENT"),
    ("plan a catch up with anita next friday at 5", "SCHEDULE_EVENT"),
    ("schedule interview with candidate on thursday at 1 pm", "SCHEDULE_EVENT"),
    ("i need a meeting with finance tomorrow at 12", "SCHEDULE_EVENT"),

    # CREATE_REMINDER
    ("remind me to call rahul at 5 pm", "CREATE_REMINDER"),
    ("set a reminder to take medicine tonight at 9", "CREATE_REMINDER"),
    ("remind me to submit the report tomorrow at 6", "CREATE_REMINDER"),
    ("create a reminder to pay the bill on monday", "CREATE_REMINDER"),
    ("please remind me about the gym tomorrow at 7 am", "CREATE_REMINDER"),
    ("ping me to email the client in 2 days", "CREATE_REMINDER"),
    ("remind me to water the plants tonight", "CREATE_REMINDER"),
    ("set reminder buy groceries tomorrow at 8 pm", "CREATE_REMINDER"),

    # GET_EVENTS
    ("what is on my calendar tomorrow", "GET_EVENTS"),
    ("show me my meetings", "GET_EVENTS"),
    ("list my upcoming events", "GET_EVENTS"),
    ("do i have anything scheduled today", "GET_EVENTS"),
    ("what does my schedule look like", "GET_EVENTS"),
    ("show my agenda for next week", "GET_EVENTS"),
    ("any appointments coming up", "GET_EVENTS"),

    # GET_REMINDERS
    ("show my reminders", "GET_REMINDERS"),
    ("what reminders do i have", "GET_REMINDERS"),
    ("list all my pending reminders", "GET_REMINDERS"),
    ("do i have any reminders today", "GET_REMINDERS"),
    ("display my reminder list", "GET_REMINDERS"),

    # DELETE_EVENT
    ("cancel my meeting with john", "DELETE_EVENT"),
    ("delete the event tomorrow", "DELETE_EVENT"),
    ("remove the appointment on friday", "DELETE_EVENT"),
    ("cancel the sync with product team", "DELETE_EVENT"),
    ("drop the review meeting from my calendar", "DELETE_EVENT"),

    # DELETE_REMINDER
    ("delete my reminder to call rahul", "DELETE_REMINDER"),
    ("remove the medicine reminder", "DELETE_REMINDER"),
    ("cancel the reminder about the report", "DELETE_REMINDER"),
    ("clear my gym reminder", "DELETE_REMINDER"),

    # SUMMARIZE_MESSAGES
    ("summarize my messages", "SUMMARIZE_MESSAGES"),
    ("give me a summary of my chats", "SUMMARIZE_MESSAGES"),
    ("what did i miss in my messages", "SUMMARIZE_MESSAGES"),
    ("summarize the conversation from today", "SUMMARIZE_MESSAGES"),
    ("brief me on my unread messages", "SUMMARIZE_MESSAGES"),
    ("condense my private messages into a short summary", "SUMMARIZE_MESSAGES"),

    # GREETING
    ("hello", "GREETING"),
    ("hi there", "GREETING"),
    ("hey assistant", "GREETING"),
    ("good morning", "GREETING"),
    ("thanks", "GREETING"),
]

INTENT_LABELS = sorted({label for _, label in INTENT_DATA})

# FR-6: intents that are pure deterministic CRUD once parsed
NON_ML_EXECUTION_INTENTS = {
    "GET_EVENTS", "GET_REMINDERS", "DELETE_EVENT", "DELETE_REMINDER",
}
