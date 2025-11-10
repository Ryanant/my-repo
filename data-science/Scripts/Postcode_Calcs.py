import pandas as pd

# 1. Read only the columns you need
df = pd.read_csv("Online_ONS_Postcode_Directory_Live_-8051680576710675916.csv", usecols=["PCD8", "LAT", "LONG"])

# 2. Derive the outcode (text before space)
df["outcode"] = df["PCD8"].str.split(" ").str[0]

# 3. Average lat/lon by outcode
outcodes = df.groupby("outcode")[["LAT", "LONG"]].mean().reset_index()

# 4. Rename columns and save
outcodes.columns = ["outcode", "latitude", "longitude"]
outcodes.to_csv("uk_outcodes.csv", index=False)

print(f"✅ Created uk_outcodes.csv with {len(outcodes)} outcodes.")
