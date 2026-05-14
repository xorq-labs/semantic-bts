---
description: Build ML pipelines with scikit-learn and xorq. Use when training models, engineering features, evaluating classifiers/regressors, or building train/test splits. Covers deferred execution, caching, and the xorq Pipeline API.
---

# ML Pipelines with xorq

xorq wraps scikit-learn pipelines with **deferred execution and caching**.
Every step (preprocessing, fit, predict) is a lazy expression that only
executes when you call `.execute()`. Results are cached — rerunning with
the same inputs skips recomputation.

## Full Pipeline Pattern

```python
from pathlib import Path

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.pipeline import Pipeline as SklearnPipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import xorq.api as xo
from xorq.caching import ParquetCache
from xorq.expr.ml import train_test_splits
from xorq.expr.ml.enums import ResponseMethod
from xorq.expr.ml.pipeline_lib import Pipeline


# 1. Load data (deferred — no execution yet)
data = xo.read_csv("data/myfile.csv")

# 2. Set up cache
con = xo.connect()
cache = ParquetCache.from_kwargs(
    source=con,
    relative_path="./tmp-cache",
    base_path=Path(".").absolute(),
)

# 3. Drop nulls in target + feature columns BEFORE splitting.
# sklearn rejects NaN in the target (`Input y contains NaN`) even when
# imputers are configured — imputers only run on features, not on y.
# xorq Tables have no `.dropna()`, so filter explicitly:
data = data.filter(
    data.deposit.notnull()
    & data.age.notnull()
    & data.balance.notnull()
    & data.duration.notnull()
)

# 4. Train/test split (deterministic, hash-based)
train_table, test_table = data.pipe(
    train_test_splits,
    test_sizes=[0.5, 0.5],   # 50/50 split
    num_buckets=2,
    random_seed=42,
)

# 4. Define sklearn pipeline
numeric_features = ["age", "balance", "duration"]
categorical_features = ["job", "marital", "education"]
all_features = numeric_features + categorical_features
target = "deposit"

preprocessor = ColumnTransformer([
    ("num", SklearnPipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ]), numeric_features),
    ("cat", SklearnPipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
        ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ]), categorical_features),
])

sklearn_pipeline = SklearnPipeline([
    ("preprocessor", preprocessor),
    ("classifier", GradientBoostingClassifier(n_estimators=50, random_state=42)),
])

# 5. Wrap with xorq — deferred + cached
xorq_pipeline = Pipeline.from_instance(sklearn_pipeline)
fitted_pipeline = xorq_pipeline.fit(
    train_table,
    features=tuple(all_features),
    target=target,
    cache=cache,
)

# 6. Predict (still deferred)
predicted_test = fitted_pipeline.predict(test_table)

# 7. Execute and evaluate
predictions_df = predicted_test.execute()
binary_predictions = predictions_df[ResponseMethod.PREDICT]

print(classification_report(predictions_df[target], binary_predictions))
print(f"AUC: {roc_auc_score(predictions_df[target], binary_predictions):.4f}")
```

## Key APIs

### Train/Test Split

```python
from xorq.expr.ml import train_test_splits

# Deterministic split using hash-based bucketing
train, test = data.pipe(
    train_test_splits,
    test_sizes=[0.8, 0.2],  # 80% train, 20% test
    num_buckets=5,
    random_seed=42,
)
```

### Wrapping sklearn Pipelines

```python
from xorq.expr.ml.pipeline_lib import Pipeline

# Wrap any sklearn Pipeline
xorq_pipeline = Pipeline.from_instance(sklearn_pipeline)

# Fit (deferred + cached)
fitted = xorq_pipeline.fit(
    train_table,
    features=tuple(feature_cols),
    target="target_column",
    cache=cache,
)

# Transform, predict, or both
transformed = fitted.transform(test_table)
predicted = fitted.predict(test_table)
```

### Caching

```python
from xorq.caching import ParquetCache

cache = ParquetCache.from_kwargs(
    source=xo.connect(),
    relative_path="./cache",
    base_path=Path(".").absolute(),
)
```

Cache is input-addressed — same inputs produce same hash, skip recomputation.

### Binary Target Encoding

```python
# Convert string labels to binary
data = data.mutate(target=(xo._["label"] == "yes").cast("int"))
```

### Accessing Predictions

```python
from xorq.expr.ml.enums import ResponseMethod

predictions_df = predicted.execute()
y_pred = predictions_df[ResponseMethod.PREDICT]       # class predictions
# y_proba = predictions_df[ResponseMethod.PREDICT_PROBA]  # probabilities (if supported)
```

## Using the xorq Catalog

Load pre-computed data from the catalog as input to ML pipelines:

```python
from xorq.catalog.catalog import Catalog

cat = Catalog.from_default()

# Load features from catalog
data = cat.load("my-features").execute()

# Or use catalog expression directly (stays lazy)
expr = cat.load("my-features")
train, test = expr.pipe(train_test_splits, ...)
```

### Cataloging Predictions

To add predictions as a new catalog entry:

```python
# exprs/my_predictions.py
import xorq.api as xo

data = xo.read_csv("data/myfile.csv")
# ... train model, get predictions ...
predictions_df = predicted.execute()
expr = xo.memtable(predictions_df)
```

Then call **`xorq_build`** (`script: "exprs/my_predictions.py"`) and **`catalog_add`** (`build_path` from the build output, `alias: ["my-predictions"]`).

## Common Expression Operations

```python
import xorq.api as xo

data = xo.read_csv("data/file.csv")

# Filter rows
filtered = data.filter(xo._.amount > 100)

# Add computed columns
enriched = data.mutate(
    ratio=xo._.col1 / xo._.col2,
    is_high=xo._.score > 0.8,
)

# Aggregate
summary = data.group_by("category").agg(
    count=xo._.col1.count(),
    avg=xo._.col1.mean(),
    total=xo._.col1.sum(),
)

# Join tables
joined = table_a.join(table_b, "shared_key")

# Select columns
selected = data.select("col1", "col2", "col3")

# Cast types
typed = data.mutate(amount=xo._.amount.cast("float64"))
```

## Tips

- **Check the catalog first** (call `catalog_list` with `kind: true`) — features may already be computed
- **Use `xorq.expr.ml.pipeline_lib.Pipeline`** to wrap sklearn pipelines for deferred execution + caching
- **Use `train_test_splits`** for deterministic, reproducible splits
- **Use `ParquetCache`** to avoid refitting models on unchanged data
- **Use `xo.memtable(df)`** to convert pandas DataFrames back to xorq expressions for cataloging
- **Keep expressions lazy** — avoid `.execute()` until you need the final result
- **Drop nulls before splitting**: sklearn rejects `NaN` in the target column with `ValueError: Input y contains NaN`. `SimpleImputer` only fills feature NaNs, not target NaNs. xorq Tables have no `.dropna()` — filter with `.filter(col.notnull() & ...)` over the target and any feature column that may contain nulls, BEFORE `train_test_splits`.
