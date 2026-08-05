import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from failure_classifier import (
    _tokenize,
    _heuristic_features,
    _build_features,
    _sigmoid,
    _logistic_predict,
    _train_logistic,
    _build_vocab,
    is_design_level_failure_learned,
    train_classifier_from_journal,
    MIN_TRAINING_SAMPLES,
)

def test_tokenize():
    assert _tokenize("Hello, World! This is a test.") == ["hello", "world", "this", "is", "a", "test"]

def test_heuristic_features():
    # Strong signal: "z-index" and "layout" -> should have positive values for strong features
    feats = _heuristic_features("z-index is broken on layout clipping")
    # Features are:
    # 0: strong design count
    # 1: medium design count
    # 2: weak design count
    # 3: code signals count
    # 4: net score
    assert feats[0] > 0
    assert feats[3] == 0
    assert feats[4] > 0

    # Code signal: "syntax error"
    feats2 = _heuristic_features("syntax error and module not found")
    assert feats2[3] > 0
    # Composite score is clamped to [0.0, 1.0], so below 0 becomes 0.0
    assert feats2[4] == 0.0

def test_build_vocab():
    docs = [
        "z-index clipping layout",
        "z-index layout alignment",
        "clipping alignment"
    ]
    vocab = _build_vocab(docs)
    # Most frequent words are "clipping", "layout", "z", "index", "alignment"
    assert "layout" in vocab
    assert "clipping" in vocab
    assert vocab["layout"] != vocab["clipping"]

def test_build_features():
    vocab = {"layout": 0, "clipping": 1}
    # Features consists of N_HEURISTIC_FEATURES (5) + MAX_VOCAB (300) = 305 features
    feats = _build_features("layout clipping", vocab)
    assert len(feats) == 305
    # Vocab features are TF-IDF values (here just word counts since pure TF-IDF is count-based inside _build_features)
    # Let's check: 5th feature is "layout" count, 6th is "clipping" count
    assert feats[5] == 0.5
    assert feats[6] == 0.5

def test_sigmoid():
    assert _sigmoid(0.0) == 0.5
    assert _sigmoid(100.0) > 0.99
    assert _sigmoid(-100.0) < 0.01

def test_logistic_predict():
    weights = [1.0, -2.0]
    intercept = 0.5
    # dot = 0.5 + 1.0 * 1.0 - 2.0 * 0.5 = 0.5 + 1.0 - 1.0 = 0.5
    # P = sigmoid(0.5) = 1 / (1 + e^-0.5) = 0.622459...
    p = _logistic_predict(weights, intercept, [1.0, 0.5])
    assert pytest.approx(p, 0.01) == 0.6224

def test_train_logistic():
    # Simple training set
    # Class 0: negative features
    # Class 1: positive features
    X = [
        [0.1, -1.0],
        [0.2, -0.8],
        [0.9, 1.0],
        [1.0, 0.8]
    ]
    y = [0, 0, 1, 1]
    weights, intercept = _train_logistic(X, y, epochs=50, lr=0.5)
    # Weights should align with predicting class correctly
    # X[2] should have P >= 0.5
    p1 = _logistic_predict(weights, intercept, X[0])
    p2 = _logistic_predict(weights, intercept, X[2])
    assert p1 < 0.5
    assert p2 > 0.5

@pytest.mark.asyncio
async def test_is_design_level_failure_learned_undertrained():
    mock_pool = AsyncMock()
    # Mock classifier not found or undertrained
    with patch("failure_classifier._load_classifier", return_value=None):
        res = await is_design_level_failure_learned(
            failure={"description": "z-index error"},
            tenant_id="tenant-1",
            pool=mock_pool
        )
        assert res is None

@pytest.mark.asyncio
async def test_is_design_level_failure_learned_success():
    mock_pool = AsyncMock()
    # Mock trained classifier
    vocab = {"layout": 0}
    weights = [0.0] * 305
    # Give layout (index 5) high positive weight
    weights[5] = 10.0
    clf = {
        "weights": weights,
        "intercept": 0.5,
        "vocab": vocab,
        "n_samples": MIN_TRAINING_SAMPLES + 5
    }
    
    with patch("failure_classifier._load_classifier", return_value=clf):
        res = await is_design_level_failure_learned(
            failure={"description": "layout clipping"},
            tenant_id="tenant-1",
            pool=mock_pool
        )
        assert res is True  # layout description + weights should yield True

@pytest.mark.asyncio
async def test_train_classifier_from_journal_insufficient():
    mock_pool = AsyncMock()
    with patch("failure_classifier._load_training_data", return_value=([], [])) as mock_load:
        await train_classifier_from_journal(mock_pool, "tenant-1", "exec-123")
        # Should not attempt to load existing classifier
        mock_load.assert_called_once()
