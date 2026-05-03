"""scripts/train_classifier.py — Entraîne et sauvegarde le modèle Naïve Bayes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.nlp.naive_bayes import NaiveBayesClassifier, TRAINING_DATA
from app.services.evaluation.evaluator import ModelEvaluator
import random, json

random.seed(42)
data = TRAINING_DATA.copy()
random.shuffle(data)
split = int(0.8 * len(data))
train = data[:split]; test = data[split:]
X_train = [t for t,_ in train]; y_train = [l for _,l in train]
X_test  = [t for t,_ in test];  y_test  = [l for _,l in test]

print("=" * 55)
print("  Estate Mind — Entraînement Naïve Bayes")
print("=" * 55)
print(f"  Train : {len(X_train)} | Test : {len(X_test)}\n")

for ngram_range in [(1,1),(1,2),(1,3)]:
    model = NaiveBayesClassifier(ngram_range=ngram_range, alpha=1.0)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    y_pred = [p.intent for p in preds]
    confs  = [p.confidence for p in preds]
    acc = sum(1 for t,p in zip(y_test,y_pred) if t==p)/len(y_test)
    perp = model.compute_perplexity(X_test)
    print(f"  N-gram {ngram_range} : accuracy={acc:.3f}, vocab={model.vectorizer.vocab_size()}, perplexity={perp:.2f}")

# Sauvegarde le meilleur modèle (bigrams)
best = NaiveBayesClassifier.from_default_dataset(ngram_range=(1,2), alpha=1.0)
Path("models").mkdir(exist_ok=True)
best.save("models/naive_bayes_intent.pkl")
print(f"\n  ✅ Modèle sauvegardé : models/naive_bayes_intent.pkl")
print(f"  Vocabulaire : {best.vectorizer.vocab_size()} features")
print(f"  Classes : {best.classes_}\n")
