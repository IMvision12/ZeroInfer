"""Cooperative cancellation for transformers generation, evaluated between tokens."""
def stopping_criteria():
    from transformers import StoppingCriteria, StoppingCriteriaList
    from runtime import stop_requested
    class Stop(StoppingCriteria):
        def __call__(self, input_ids, scores, **kwargs):
            return stop_requested()
    return StoppingCriteriaList([Stop()])
