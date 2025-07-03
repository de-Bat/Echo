# price_tracker_app/ai/models/simple_heuristic_model.py

from typing import Dict, Tuple
import logging

from price_tracker_app.core.models import RecommendationAction

logger = logging.getLogger(__name__)

class SimpleHeuristicModel:
    """
    A simple heuristic-based model for value prediction recommendations.
    Adjusted to use generic 'value' instead of 'price'.
    """
    # Config for Heuristics
    BUY_BELOW_MA30_PCT_THRESHOLD: float = -7.0
    STRONG_BUY_BELOW_MA30_PCT_THRESHOLD: float = -15.0
    BUY_RECENT_DROP_PCT_THRESHOLD: float = -10.0
    SALE_APPROACHING_DAYS_THRESHOLD: int = 14

    DEFAULT_CERTAINTY: float = 0.60
    DEFAULT_ACCURACY: float = 0.50

    def __init__(self, config: Dict = None):
        if config:
            for key, value in config.items():
                if hasattr(self, key.upper()):
                    setattr(self, key.upper(), value)

        self.reasoning_priority = [
            "STRONG_BUY_VALUE_VS_MA30", # Renamed for clarity
            "BUY_VALUE_VS_MA30",      # Renamed
            "BUY_RECENT_SIGNIFICANT_DROP",
            "WAIT_SALE_APPROACHING", # This rule should only apply if item_is_monetary
            "HOLD_STABLE_VALUE",      # Renamed
        ]

    def predict(self, features: Dict[str, any]) -> Tuple[RecommendationAction, float, float, str]:
        """
        Makes a prediction based on the extracted features.
        Features dictionary now includes 'current_value', 'item_is_monetary', etc.
        """
        reasons = {}
        item_is_monetary = features.get("item_is_monetary", False)
        # Use "Value" for non-monetary items in reasoning, "Price" for monetary.
        value_label = "Price" if item_is_monetary else "Value"

        logger.debug(f"SimpleHeuristicModel predicting for features: {features}")

        # Rule 1: Strong Buy based on significant drop below 30-day MA
        if features.get("change_from_30d_avg_pct") is not None:
            if features["change_from_30d_avg_pct"] < self.STRONG_BUY_BELOW_MA30_PCT_THRESHOLD:
                reasons["STRONG_BUY_VALUE_VS_MA30"] = (
                    RecommendationAction.BUY,
                    self.DEFAULT_ACCURACY + 0.2,
                    self.DEFAULT_CERTAINTY + 0.15,
                    f"{value_label} is {features['change_from_30d_avg_pct']:.1f}% below 30-day average (Threshold: {self.STRONG_BUY_BELOW_MA30_PCT_THRESHOLD}%) - Strong Buy Signal."
                )

        # Rule 2: Buy based on drop below 30-day MA
        if features.get("change_from_30d_avg_pct") is not None:
            if features["change_from_30d_avg_pct"] < self.BUY_BELOW_MA30_PCT_THRESHOLD:
                reasons["BUY_VALUE_VS_MA30"] = (
                    RecommendationAction.BUY,
                    self.DEFAULT_ACCURACY + 0.1,
                    self.DEFAULT_CERTAINTY + 0.1,
                    f"{value_label} is {features['change_from_30d_avg_pct']:.1f}% below 30-day average (Threshold: {self.BUY_BELOW_MA30_PCT_THRESHOLD}%)."
                )

        # Rule 3: Buy based on recent significant drop compared to 7-day MA
        if features.get("change_from_7d_avg_pct") is not None:
            if features["change_from_7d_avg_pct"] < self.BUY_RECENT_DROP_PCT_THRESHOLD:
                reasons["BUY_RECENT_SIGNIFICANT_DROP"] = (
                    RecommendationAction.BUY,
                    self.DEFAULT_ACCURACY + 0.05,
                    self.DEFAULT_CERTAINTY + 0.05,
                    f"{value_label} recently dropped significantly: {features['change_from_7d_avg_pct']:.1f}% below 7-day average (Threshold: {self.BUY_RECENT_DROP_PCT_THRESHOLD}%)."
                )

        # Rule 4: Wait if a sale is approaching (only for monetary items)
        if item_is_monetary: # This check is crucial
            days_to_sale = features.get("days_to_next_sale")
            if days_to_sale is not None and 0 <= days_to_sale <= self.SALE_APPROACHING_DAYS_THRESHOLD:
                reasons["WAIT_SALE_APPROACHING"] = (
                    RecommendationAction.WAIT,
                    self.DEFAULT_ACCURACY + 0.1,
                    self.DEFAULT_CERTAINTY + 0.1,
                    f"A known sale event is approaching in {days_to_sale} days. Consider waiting."
                )

        # --- Determine final recommendation based on priority ---
        for reason_key in self.reasoning_priority:
            if reason_key in reasons:
                logger.info(f"Heuristic matched: {reason_key} - Action: {reasons[reason_key][0].value}")
                return reasons[reason_key]

        # Default/Fallback Recommendation
        reasons["HOLD_STABLE_VALUE"] = (
            RecommendationAction.HOLD,
            self.DEFAULT_ACCURACY - 0.1,
            self.DEFAULT_CERTAINTY,
            f"{value_label} is relatively stable or no strong buy/wait signals detected."
        )
        logger.info(f"No specific heuristic matched. Defaulting to HOLD_STABLE_VALUE.")
        return reasons["HOLD_STABLE_VALUE"]


if __name__ == "__main__":
    # Setup basic logging if run directly
    from price_tracker_app.logging_config import setup_logging
    setup_logging(level=logging.DEBUG)

    logger.info("--- Testing SimpleHeuristicModel (Refactored for Generic Value) ---")
    model = SimpleHeuristicModel()

    # Test Case 1: Strong Buy Signal (Monetary Item)
    features_strong_buy = {
        "item_is_monetary": True,
        "current_value": 80.0,
        "moving_avg_30d": 100.0,
        "change_from_30d_avg_pct": -20.0,
        "moving_avg_7d": 85.0,
        "change_from_7d_avg_pct": -5.88,
        "days_to_next_sale": 30
    }
    action, acc, cert, reason = model.predict(features_strong_buy)
    logger.info(f"\nTest Case 1 (Strong Buy - Monetary): Action: {action.value}, Accuracy: {acc:.2f}, Certainty: {cert:.2f}, Reason: {reason}")
    assert action == RecommendationAction.BUY

    # Test Case 2: Wait, Sale Approaching (Monetary Item)
    features_wait_sale_monetary = {
        "item_is_monetary": True,
        "current_value": 90.0,
        "moving_avg_30d": 100.0,
        "change_from_30d_avg_pct": -10.0, # Qualifies for BUY_VALUE_VS_MA30
        "moving_avg_7d": 92.0,
        "change_from_7d_avg_pct": -2.17,
        "days_to_next_sale": 5 # Sale is very soon
    }
    # To ensure WAIT_SALE_APPROACHING wins, it needs higher priority
    model_sale_priority = SimpleHeuristicModel()
    model_sale_priority.reasoning_priority = [
            "WAIT_SALE_APPROACHING", # Moved up
            "STRONG_BUY_VALUE_VS_MA30",
            "BUY_VALUE_VS_MA30",
            "BUY_RECENT_SIGNIFICANT_DROP",
            "HOLD_STABLE_VALUE",
    ]
    action_sp, acc_sp, cert_sp, reason_sp = model_sale_priority.predict(features_wait_sale_monetary)
    logger.info(f"\nTest Case 2 (Wait - Sale, Monetary, Custom Priority): Action: {action_sp.value}, Accuracy: {acc_sp:.2f}, Certainty: {cert_sp:.2f}, Reason: {reason_sp}")
    assert action_sp == RecommendationAction.WAIT

    # Test Case 3: Hold (Non-Monetary Item, e.g. quote count)
    features_hold_non_monetary = {
        "item_is_monetary": False,
        "current_value": 10.0, # e.g., 10 quotes
        "moving_avg_30d": 9.0,
        "change_from_30d_avg_pct": 11.1, # Value increased
        "moving_avg_7d": 10.0,
        "change_from_7d_avg_pct": 0.0,
        "days_to_next_sale": None # Not applicable or not found
    }
    action_nm, acc_nm, cert_nm, reason_nm = model.predict(features_hold_non_monetary)
    logger.info(f"\nTest Case 3 (Hold - Non-Monetary): Action: {action_nm.value}, Accuracy: {acc_nm:.2f}, Certainty: {cert_nm:.2f}, Reason: {reason_nm}")
    assert action_nm == RecommendationAction.HOLD

    # Test Case 4: Buy (Non-Monetary Item, value dropped significantly)
    features_buy_non_monetary = {
        "item_is_monetary": False,
        "current_value": 5.0, # e.g., quote count dropped from 10 to 5
        "moving_avg_30d": 10.0,
        "change_from_30d_avg_pct": -50.0, # Significant drop
        "moving_avg_7d": 8.0,
        "change_from_7d_avg_pct": -37.5,
        "days_to_next_sale": None
    }
    action_buy_nm, acc_buy_nm, cert_buy_nm, reason_buy_nm = model.predict(features_buy_non_monetary)
    logger.info(f"\nTest Case 4 (Buy - Non-Monetary, Value Drop): Action: {action_buy_nm.value}, Accuracy: {acc_buy_nm:.2f}, Certainty: {cert_buy_nm:.2f}, Reason: {reason_buy_nm}")
    assert action_buy_nm == RecommendationAction.BUY


    logger.info("\nSimpleHeuristicModel tests (refactored) completed.")
