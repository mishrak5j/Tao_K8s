import time
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier

print("🚀 Pipeline Check: Starting Random Forest Task...")
start_time = time.time()

# Generate dataset
X, y = make_classification(n_samples=50000, n_features=20, random_state=42)

# Train model (using all cores via n_jobs=-1)
model = RandomForestClassifier(n_estimators=100, n_jobs=-1)
model.fit(X, y)

duration = time.time() - start_time
print(f"✅ Task Successful! Training Time: {duration:.2f} seconds")