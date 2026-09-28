from paper_diff.stage1_compute_objective_metrics import compute_metrics


def test_word_and_sentence_counts():
    md_a = "One two three. Four five six seven!"
    md_b = "Alpha beta."

    metrics = compute_metrics(md_a, md_b)

    assert metrics["word_count_a"] == 7
    assert metrics["word_count_b"] == 2
    assert metrics["sentence_count_a"] == 2
    assert metrics["sentence_count_b"] == 1


def test_jaccard_similarity_of_identical_text_is_one():
    metrics = compute_metrics("The quick brown fox", "The quick brown fox")
    assert metrics["jaccard_similarity"] == 1.0


def test_jaccard_similarity_of_disjoint_text_is_zero():
    metrics = compute_metrics("apple banana", "carrot potato")
    assert metrics["jaccard_similarity"] == 0.0


def test_jaccard_similarity_is_case_insensitive():
    metrics = compute_metrics("Apple Banana", "apple banana")
    assert metrics["jaccard_similarity"] == 1.0


def test_jaccard_similarity_partial_overlap():
    metrics = compute_metrics("apple banana carrot", "apple banana potato")
    # intersection {apple, banana} = 2, union {apple, banana, carrot, potato} = 4
    assert metrics["jaccard_similarity"] == 0.5
