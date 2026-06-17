from pathlib import Path
from langsmith import Client
from yaml import safe_load

def create_dataset(file_name: Path) -> None:
    client = Client()

    dataset = client.create_dataset(
        dataset_name="Assistant dataset",
        description="Tests the interactions with the Assistant"
    )

    examples = safe_load(file_name.read_text())
    

    # Add examples to the dataset
    client.create_examples(dataset_id=dataset.id, examples=examples)

