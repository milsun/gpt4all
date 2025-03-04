import glob
import torch
from datasets import load_dataset
import os
from torch.utils.data import DataLoader
from transformers import DefaultDataCollator

IGNORE_INDEX = -100

# The tokenization function
# def tokenize_inputs(config, tokenizer, example):
#     tokens = tokenizer(example['content'] + tokenizer.eos_token, padding="max_length", truncation=True, max_length=config['max_length'])
    
#     return tokens

# # Apply the tokenizer in batch mode and drop all the columns except the tokenization result
# train_token = train.map(tokenization, batched = True, remove_columns=["title", "abstract", "Unnamed: 0", "Unnamed: 0.1"], num_proc=10)
# val_token = val.map(tokenization, batched = True, remove_columns=["title", "abstract", "Unnamed: 0", "Unnamed: 0.1"], num_proc=10)

def tokenize_inputs(config, tokenizer, examples):
    max_length = config["max_length"]
    input_ids = torch.full((len(examples["content"]), max_length), tokenizer.pad_token_id)

    out = {"labels": [], "attention_mask": []}
    for i, content in enumerate(examples["content"]):
        input_tokens = tokenizer(content, truncation=True, max_length=max_length, return_tensors="pt")["input_ids"].squeeze()
        input_len = len(input_tokens)

        input_ids[i, :input_len] = input_tokens

        # add eos token, enforce stopping if we don't truncate 
        # we don't want long code to stop generating if truncated during training
        if len(input_tokens) < max_length:
            input_ids[i, len(input_tokens)] = tokenizer.eos_token_id

        labels = input_ids[i].clone()
        labels[labels == tokenizer.pad_token_id] = IGNORE_INDEX
        # to debug this, can set all values == -100 to the pad token, then assert that tokenizer.decode(labels, skip_special_tokens=True).strip() == response

        attention_mask = input_ids[i].ne(tokenizer.pad_token_id).int()

        out["labels"].append(labels)
        out["attention_mask"].append(attention_mask)

    out["input_ids"] = input_ids

    out = {k: torch.stack(v) if isinstance(v, list) else v for k, v in out.items()}

    return out

def load_data(config, tokenizer):
    dataset_path = config["dataset_path"]

    if os.path.exists(dataset_path):
        # check if path is a directory
        if os.path.isdir(dataset_path):
            files = glob.glob(os.path.join(dataset_path, "*_clean.jsonl"))
        else:
            files = [dataset_path]

        print(f"Reading files {files}")

        dataset = load_dataset("json", data_files=files, split="train")

    else:
        dataset = load_dataset(dataset_path)

    dataset = dataset.train_test_split(test_size=.05, seed=config["seed"])

    train_dataset, val_dataset = dataset["train"], dataset["test"]

    if config["streaming"] is False:
        kwargs = {"num_proc": config["num_proc"]}
    else:
        kwargs = {}

    # tokenize inputs and return labels and attention mask
    train_dataset = train_dataset.map(
        lambda ele: tokenize_inputs(config, tokenizer, ele),
        batched=True,
        **kwargs
    )
    val_dataset = val_dataset.map(
        lambda ele: tokenize_inputs(config, tokenizer, ele), 
        batched=True,
        **kwargs
    )

    train_dataset = train_dataset.with_format("torch")
    val_dataset = val_dataset.with_format("torch")

    # create dataloader with default data collator since we already have labels

    train_dataloader = DataLoader(
        train_dataset,
        collate_fn=DefaultDataCollator(),
        batch_size=config["batch_size"],
    )

    val_dataloader = DataLoader(
        val_dataset,
        collate_fn=DefaultDataCollator(),
        batch_size=config["batch_size"],
    )

    return train_dataloader, val_dataloader
