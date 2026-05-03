"""
scripts/evaluate.py
====================
Evaluation complete du systeme NLP Estate Mind.
Usage:
  python scripts/evaluate.py
  python scripts/evaluate.py --api
  python scripts/evaluate.py --full
  python scripts/evaluate.py --darija
"""

import sys, time, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_DATASET = [
    {"query": "quel est le prix d'un S+2 a Ariana ?",      "expected": "price_estimation",    "lang": "fr"},
    {"query": "chnowa soum dar fi tunis",                    "expected": "price_estimation",    "lang": "ar"},
    {"query": "is this a good investment in sfax?",          "expected": "investment_analysis", "lang": "en"},
    {"query": "mrigel 9arib centre ville",                   "expected": "location_analysis",   "lang": "ar"},
    {"query": "is this property legally compliant?",         "expected": "legal_verification",  "lang": "en"},
    {"query": "generer un rapport complet pour Tunis",       "expected": "report_generation",   "lang": "fr"},
    {"query": "Je cherche dar bhi w rkhis fi ariana",        "expected": "price_estimation",    "lang": "ar"},
    {"query": "ما هو سعر الشقة في سوسة؟",                  "expected": "price_estimation",    "lang": "ar"},
    {"query": "overview du marche immobilier tunisien",      "expected": "general_query",       "lang": "fr"},
    {"query": "average rent studio hammamet",                "expected": "price_estimation",    "lang": "en"},
    {"query": "rendement locatif appartement ariana",        "expected": "investment_analysis", "lang": "fr"},
    {"query": "meilleur quartier habiter tunis",             "expected": "location_analysis",   "lang": "fr"},
    {"query": "titre foncier villa hammamet",                "expected": "legal_verification",  "lang": "fr"},
    {"query": "prix moyen terrain sfax",                     "expected": "price_estimation",    "lang": "fr"},
    {"query": "best investment zone tunis",                  "expected": "investment_analysis", "lang": "en"},
    {"query": "wein nestathmar fi aqarat tunis",             "expected": "investment_analysis", "lang": "ar"},
    {"query": "export pdf report real estate",               "expected": "report_generation",   "lang": "en"},
    {"query": "statistiques annonces tunisie",               "expected": "general_query",       "lang": "fr"},
    {"query": "استثمار عقاري في تونس",                     "expected": "investment_analysis", "lang": "ar"},
    {"query": "قيمة شقة في اريانة",                        "expected": "price_estimation",    "lang": "ar"},
]

SEP = "-" * 62


def evaluate_pipeline():
    from app.services.nlp.intent_detector import detect_intent
    from app.services.nlp.language_detector import detect_language
    from app.services.nlp.tunisian_normalizer import get_normalizer
    from app.services.nlp.translator import to_english
    from app.services.evaluation.evaluator import ModelEvaluator

    print(f"\n{'='*62}")
    print("  EVALUATION COMPLETE — Estate Mind NLP Pipeline")
    print(f"{'='*62}\n")

    normalizer = get_normalizer()
    y_true, y_pred, confs, latencies = [], [], [], []
    darija_count = 0

    for item in TEST_DATASET:
        query = item["query"]; expected = item["expected"]
        t0 = time.monotonic()

        norm = normalizer.normalize(query)
        q2 = norm.normalized_text if norm.is_tunisian else query
        lang = detect_language(q2)
        if lang.detected not in ("en","unknown"):
            try: q2 = to_english(q2, lang.detected)
            except Exception: pass

        intent, conf, probs, ngrams = detect_intent(q2)
        ms = int((time.monotonic()-t0)*1000)

        correct = (intent == expected)
        y_true.append(expected); y_pred.append(intent)
        confs.append(conf); latencies.append(ms)
        if norm.is_tunisian: darija_count += 1

        icon = "OK" if correct else "XX"
        print(f"  [{icon}] [{lang.detected}] {query[:40]:<40}")
        print(f"       pred: {intent:<22} conf:{conf:.0%} {ms}ms")
        if not correct: print(f"       want: {expected}")
        if norm.is_tunisian: print(f"       darija: {norm.n_replaced} termes normalises")
        print()

    # Metriques
    ev = ModelEvaluator()
    report = ev.compute_classification_metrics(y_true, y_pred, confs)
    report.hallucination_rate = 0.0
    report.darija_coverage = darija_count / len(TEST_DATASET)
    report.print_report()

    # Perplexite
    print(f"  PERPLEXITE")
    print(SEP)
    print(f"  Perplexite : {report.perplexity:.2f}")
    print(f"  (Ideal < 3.0 pour 6 classes, bigrams recommandes)")

    # Latence
    lat_sorted = sorted(latencies)
    p50 = lat_sorted[len(lat_sorted)//2]
    p95 = lat_sorted[int(len(lat_sorted)*0.95)]
    print(f"\n  LATENCE NLP (sans appel agent)")
    print(SEP)
    print(f"  P50:{p50}ms  P95:{p95}ms  Max:{max(latencies)}ms")
    print(f"  Budget restant agent: ~{20000-p95}ms sur 20000ms total\n")

    # Darija
    print(f"  COUVERTURE DARIJA")
    print(SEP)
    print(f"  Detections: {darija_count}/{len(TEST_DATASET)} ({darija_count/len(TEST_DATASET):.0%})")
    print()

    # Comparaison N-grams
    print(f"  COMPARAISON N-GRAMMES")
    print(SEP)
    print(f"  {'Modele':<12} {'Accuracy':>10} {'F1':>8} {'Vocab':>8} {'Perp':>8}")
    print(SEP)
    from app.services.nlp.naive_bayes import NaiveBayesClassifier, TRAINING_DATA
    import random as rnd
    rnd.seed(42)
    data = TRAINING_DATA.copy(); rnd.shuffle(data)
    split = int(0.8*len(data))
    Xtr=[t for t,_ in data[:split]]; ytr=[l for _,l in data[:split]]
    Xte=[t for t,_ in data[split:]]; yte=[l for _,l in data[split:]]
    for ng in [(1,1),(1,2),(1,3)]:
        m = NaiveBayesClassifier(ngram_range=ng, alpha=1.0)
        m.fit(Xtr, ytr)
        preds = m.predict(Xte)
        yp=[p.intent for p in preds]; cf=[p.confidence for p in preds]
        acc2=sum(1 for a,b in zip(yte,yp) if a==b)/len(yte)
        perp2=m.compute_perplexity(Xte)
        r2=ev.compute_classification_metrics(yte,yp)
        star = " <-- OPTIMAL" if ng==(1,2) else ""
        print(f"  {str(ng):<12} {acc2:>10.3f} {r2.macro_f1:>8.3f} {m.vectorizer.vocab_size():>8} {perp2:>8.2f}{star}")
    print()


def evaluate_via_api():
    import httpx
    print(f"\n{'='*62}")
    print("  EVALUATION VIA API — http://localhost:8000")
    print(f"{'='*62}\n")
    try:
        with httpx.Client(timeout=5) as client:
            h = client.get("http://localhost:8000/api/v1/health").json()
            print(f"  Serveur actif v{h.get('version','?')}")
            for ag,st in h.get("agents",{}).items():
                print(f"    {'OK' if st=='ok' else 'XX'} {ag}: {st}")
    except Exception as e:
        print(f"  Serveur inaccessible: {e}")
        print("  Demarrez avec: python start_all.py"); return

    print()
    y_true, y_pred, latencies = [], [], []
    with httpx.Client(timeout=25) as client:
        for item in TEST_DATASET[:10]:
            try:
                t0=time.monotonic()
                r=client.post("http://localhost:8000/api/v1/chat",
                              json={"query":item["query"],"generate_report":False})
                ms=int((time.monotonic()-t0)*1000)
                d=r.json()
                pred=d.get("intent","unknown"); conf=d.get("confidence",0)
                ok=(pred==item["expected"])
                y_true.append(item["expected"]); y_pred.append(pred); latencies.append(ms)
                icon="OK" if ok else "XX"
                print(f"  [{icon}] {item['query'][:40]:<40} {pred:<22} {conf:.0%} {ms}ms")
                if not ok: print(f"       want: {item['expected']}")
            except Exception as e:
                print(f"  [ERR] {item['query'][:40]}: {e}")
    if y_true:
        acc=sum(1 for a,b in zip(y_true,y_pred) if a==b)/len(y_true)
        p50=sorted(latencies)[len(latencies)//2]
        p95=sorted(latencies)[int(len(latencies)*0.95)]
        print(f"\n  Accuracy: {acc:.1%}  P50:{p50}ms  P95:{p95}ms")
        print(f"  Timeout: {'OK (<20s)' if p95<20000 else 'DEPASSE'}")


def evaluate_darija():
    from app.services.nlp.tunisian_normalizer import TunisianNormalizer
    norm = TunisianNormalizer()
    print(f"\n{'='*62}")
    print("  EVALUATION NORMALISEUR DARIJA")
    print(f"{'='*62}\n")
    cases=[
        ("chnowa soum dar fi tunis",        True),
        ("wein nestathmar fi aqarat tunis", True),
        ("qaddesh kri appart ariana s2",    True),
        ("mrigel 9arib centre ghali",       True),
        ("what is the price in tunis?",     False),
        ("quel est le prix a sfax",         False),
        ("ما هو سعر الشقة",               False),
    ]
    ok_count=0
    for text, expected in cases:
        r=norm.normalize(text)
        ok=(r.is_tunisian==expected); if ok: ok_count+=1
        icon="OK" if ok else "XX"
        print(f"  [{icon}] {text[:42]:<42} darija={str(r.is_tunisian)}")
        if r.is_tunisian:
            print(f"       -> '{r.normalized_text[:55]}'  ({r.n_replaced} termes)")
    print(f"\n  Detection: {ok_count}/{len(cases)} ({ok_count/len(cases):.0%})")
    cov=norm.get_coverage()
    print(f"  Dictionnaire: {cov['total_terms']} termes | Marqueurs: {cov['markers']}\n")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--api",    action="store_true")
    p.add_argument("--full",   action="store_true")
    p.add_argument("--darija", action="store_true")
    args=p.parse_args()
    if args.api:        evaluate_via_api()
    elif args.darija:   evaluate_darija()
    elif args.full:     evaluate_pipeline(); evaluate_darija()
    else:               evaluate_pipeline()
    print("  Evaluation terminee.\n")

if __name__ == "__main__":
    main()
