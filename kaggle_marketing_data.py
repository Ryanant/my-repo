import pandas as pd
import os

# Set dataset path
data_path = r"C:\Users\jackj\.cache\kagglehub\datasets\faviovaz\marketing-ab-testing\versions\1"

# Load the dataset
df = pd.read_csv(os.path.join(data_path, "marketing_ab.csv"))  # adjust file name if needed

# Peek at the data
print(df.head())
print(df.info())