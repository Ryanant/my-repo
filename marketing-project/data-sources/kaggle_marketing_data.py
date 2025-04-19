# kaggle_marketing_data.py
import pandas as pd
import os

data_path = r"C:\Users\jackj\.cache\kagglehub\datasets\faviovaz\marketing-ab-testing\versions\1"
file_name = "marketing_ab.csv"  # adjust if different

def load_data():
    df = pd.read_csv(os.path.join(data_path, file_name))
    return df
