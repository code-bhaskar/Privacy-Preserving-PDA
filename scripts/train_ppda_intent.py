import os
import random
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import numpy as np

from app.Data_sets.intent.intent_seed import INTENT_DATA, INTENT_LABELS
from fl.model.net import IntentNet
from fl.data.dataset import IntentDataset, collate

# Expand seed dataset into ~2000 utterances with realistic variations
TEMPLATES = {
    "SCHEDULE_EVENT": [
        "schedule a meeting with {who} {when}",
        "book a meeting with {who} {when}",
        "put an event with {who} on my calendar {when}",
        "set up a call with {who} {when}",
        "add an appointment with {who} {when}",
        "arrange a sync with {who} {when}",
        "create a calendar event for {what} {when}",
        "plan a catch up with {who} {when}",
        "schedule interview with {who} {when}",
        "i need a meeting with {who} {when}",
        "organize a discussion with {who} {when}",
        "block time for {what} {when}",
    ],
    "CREATE_REMINDER": [
        "remind me to {task} {when}",
        "set a reminder to {task} {when}",
        "remind me about {task} {when}",
        "create a reminder to {task} {when}",
        "please remind me to {task} {when}",
        "ping me to {task} {when}",
        "notify me to {task} {when}",
        "set reminder for {task} {when}",
        "don't forget to {task} {when}",
    ],
    "GET_EVENTS": [
        "what is on my calendar {when}",
        "show me my meetings {when}",
        "list my upcoming events",
        "do i have anything scheduled {when}",
        "what does my schedule look like {when}",
        "show my agenda for {when}",
        "any appointments coming up",
        "check my calendar for {when}",
        "what events do i have",
        "view calendar schedule",
    ],
    "GET_REMINDERS": [
        "show my reminders",
        "what reminders do i have",
        "list all my pending reminders",
        "do i have any reminders today",
        "display my reminder list",
        "check my reminders",
        "view pending tasks",
        "show all reminders",
        "what do i need to do today",
    ],
    "DELETE_EVENT": [
        "cancel my meeting with {who}",
        "delete the event {when}",
        "remove the appointment on {when}",
        "cancel the sync with {who}",
        "drop the review meeting from my calendar",
        "delete meeting with {who}",
        "cancel calendar appointment",
        "clear event from schedule",
    ],
    "DELETE_REMINDER": [
        "delete my reminder to {task}",
        "remove the {task} reminder",
        "cancel the reminder about {task}",
        "clear my {task} reminder",
        "delete reminder {task}",
        "dismiss reminder",
        "remove task from reminders",
    ],
    "SUMMARIZE_MESSAGES": [
        "summarize my messages",
        "give me a summary of my chats",
        "what did i miss in my messages",
        "summarize the conversation from {when}",
        "brief me on my unread messages",
        "condense my private messages into a short summary",
        "recap my unread chats",
        "summarize recent conversation",
        "give me a brief summary of messages",
    ],
    "GREETING": [
        "hello",
        "hi there",
        "hey assistant",
        "good morning",
        "good afternoon",
        "good evening",
        "thanks",
        "thank you very much",
        "hello there",
        "hey how are you",
    ],
}

WHOS = ["john", "sarah", "rahul", "anita", "finance team", "product team", "the client", "alex", "the doctor", "engineering"]
WHENS = ["tomorrow at 10", "next monday at 3", "friday at 2 pm", "tomorrow morning", "wednesday at 11", "day after tomorrow", "today at 4", "tonight at 8", "next week"]
TASKS = ["call rahul", "take medicine", "submit the report", "pay the bill", "water the plants", "buy groceries", "email the team", "review the code", "go to the gym"]
WHATS = ["project review", "budget sync", "team retrospective", "design critique", "1 on 1", "sprint planning"]


def build_synthetic_corpus() -> list[tuple[str, int]]:
    label_to_id = {label: i for i, label in enumerate(INTENT_LABELS)}
    corpus = []

    # Include original seed
    for text, label in INTENT_DATA:
        corpus.append((text, label_to_id[label]))

    # Generate synthetic utterances
    rng = random.Random(42)
    for intent, templates in TEMPLATES.items():
        label_id = label_to_id[intent]
        for _ in range(260):
            tpl = rng.choice(templates)
            utt = tpl.format(
                who=rng.choice(WHOS),
                when=rng.choice(WHENS),
                task=rng.choice(TASKS),
                what=rng.choice(WHATS),
            )
            corpus.append((utt, label_id))

    rng.shuffle(corpus)
    return corpus


def train_and_export(output_path: str = "deployed_models/intent_model.onnx"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    corpus = build_synthetic_corpus()
    split = int(len(corpus) * 0.85)
    train_data, val_data = corpus[:split], corpus[split:]

    train_ds = IntentDataset(train_data)
    val_ds = IntentDataset(val_data)
    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True, collate_fn=collate)
    val_loader = DataLoader(val_ds, batch_size=64, shuffle=False, collate_fn=collate)

    model = IntentNet(num_classes=len(INTENT_LABELS))
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.005, weight_decay=1e-5)

    best_acc = 0.0
    for epoch in range(15):
        model.train()
        for text_idx, offsets, labels in train_loader:
            optimizer.zero_grad()
            out = model(text_idx, offsets)
            loss = criterion(out, labels)
            loss.backward()
            optimizer.step()

        model.eval()
        correct, total = 0, 0
        with torch.no_grad():
            for text_idx, offsets, labels in val_loader:
                out = model(text_idx, offsets)
                preds = out.argmax(dim=-1)
                correct += (preds == labels).sum().item()
                total += len(labels)
        acc = correct / total
        if acc > best_acc:
            best_acc = acc

    print(f"Trained IntentNet validation accuracy: {best_acc * 100:.2f}%")

    # Export to ONNX
    model.eval()
    dummy_text = torch.tensor([1, 2, 3, 4], dtype=torch.long)
    dummy_offsets = torch.tensor([0], dtype=torch.long)

    torch.onnx.export(
        model,
        (dummy_text, dummy_offsets),
        output_path,
        input_names=["tokens", "offsets"],
        output_names=["logits"],
        dynamic_axes={
            "tokens": {0: "num_tokens"},
            "offsets": {0: "batch_size"},
            "logits": {0: "batch_size"},
        },
        opset_version=14,
    )
    print(f"Exported ONNX model to {output_path} ({os.path.getsize(output_path) / 1024:.1f} KB)")


if __name__ == "__main__":
    train_and_export()
