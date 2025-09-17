# scripts/ab_test_analysis.py

from pathlib import Path
import sys
import pandas as pd
from scipy import stats

# Add parent dir to path so we can import from data-sources
base_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(base_dir / "data-sources"))

from kaggle_marketing_data import load_data

# Load the dataset
df = load_data()

# Clean column names (optional but nice)
df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

# Drop index column if needed
df = df.drop(columns=['unnamed:_0'], errors='ignore')

# Make sure 'converted' is boolean or 0/1
df['converted'] = df['converted'].astype(int)

# Check group labels
print("Test groups found:", df['test_group'].unique())

# Rename for clarity if needed
control_group = 'no_ad'  # replace with actual label if different
treatment_group = 'ad'

# Split groups
control = df[df['test_group'] == control_group]['converted']
treatment = df[df['test_group'] == treatment_group]['converted']

# Run a t-test
t_stat, p_val = stats.ttest_ind(treatment, control)

# Report
print(f"\nControl Conversion Rate: {control.mean():.4%}")
print(f"Treatment Conversion Rate: {treatment.mean():.4%}")
print(f"Lift: {(treatment.mean() - control.mean()):.4%}")
print(f"T-statistic: {t_stat:.4f}")
print(f"P-value: {p_val:.4f}")

if p_val < 0.05:
    print("🔍 Statistically significant difference between groups (p < 0.05)")
else:
    print("🟢 No significant difference between groups (p ≥ 0.05)")
