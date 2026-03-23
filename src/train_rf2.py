import time
from sklearn.datasets import fetch_openml
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

print("🌲 Task: Random Forest on 'Covertype' Dataset (Real-world Benchmark)")
start_time = time.time()

# 1. Fetch data (Real-world data from OpenML)
print("📥 Downloading Covertype dataset...")
# 'covertype' id is 180. Using a subset to keep it within your limits.
X, y = fetch_openml(data_id=180, return_X_y=True, as_frame=False, parser="liac-arff")

# 2. Preprocess (Sub-sampling for 1GB RAM safety)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, train_size=0.2, random_state=42
)
print(f"📊 Training on {X_train.shape[0]} samples with {X_train.shape[1]} features")

# 3. Heavy Training
# Increasing depth and estimators to stress the CPU
model = RandomForestClassifier(n_estimators=150, max_depth=20, n_jobs=-1)
model.fit(X_train, y_train)

duration = time.time() - start_time
print(f"✅ Training Complete! Score: {model.score(X_test, y_test):.4f}")
print(f"⏱️ TOTAL CLOUD DURATION: {duration:.2f} seconds")
