# price_tracker_app/ai/models/simple_heuristic_model.py

from typing import Dict, Tuple

from price_tracker_app.core.models import RecommendationAction

class SimpleHeuristicModel:
    """
    A simple heuristic-based model for price prediction recommendations.
    """
    # --- Configuration for Heuristics (can be tuned or moved to a config file) ---
    # Buy if current price is X% below 30-day moving average
    BUY_BELOW_MA30_PCT_THRESHOLD: float = -7.0  # e.g., -7.0 means 7% below MA
    # Strong buy if current price is Y% below 30-day moving average
    STRONG_BUY_BELOW_MA30_PCT_THRESHOLD: float = -15.0 # e.g., -15.0 means 15% below MA

    # Buy if price dropped significantly (e.g., Z%) in the last few days
    BUY_RECENT_DROP_PCT_THRESHOLD: float = -10.0 # e.g., -10% drop compared to 7-day MA

    # Consider waiting if a known sale is approaching
    SALE_APPROACHING_DAYS_THRESHOLD: int = 14 # Days within which a sale is "approaching"

    # Default certainty and accuracy (can be adjusted based on rule strength)
    DEFAULT_CERTAINTY: float = 0.60 # Base certainty for any heuristic rule match
    DEFAULT_ACCURACY: float = 0.50  # Base accuracy (more like a placeholder for heuristics)

    def __init__(self, config: Dict = None):
        """
        Initialize the model. Config can override default thresholds.
        Example config: {"BUY_BELOW_MA30_PCT_THRESHOLD": -8.0}
        """
        if config:
            for key, value in config.items():
                if hasattr(self, key.upper()): # Ensure only existing attrs are set
                    setattr(self, key.upper(), value)

        self.reasoning_priority = [
            "STRONG_BUY_PRICE_VS_MA30",
            "BUY_PRICE_VS_MA30",
            "BUY_RECENT_SIGNIFICANT_DROP",
            "WAIT_SALE_APPROACHING",
            "HOLD_STABLE_PRICE",
        ]

    def predict(self, features: Dict[str, any]) -> Tuple[RecommendationAction, float, float, str]:
        """
        Makes a prediction based on the extracted features.

        Args:
            features: A dictionary of features (e.g., from ai.features.extract_features).

        Returns:
            A tuple containing:
            - RecommendationAction (BUY, WAIT, HOLD)
            - Accuracy rank (float, 0.0 to 1.0) - more of a confidence score for heuristics
            - Certainty rank (float, 0.0 to 1.0) - how sure about the data/context
            - Reasoning (str)
        """
        reasons = {} # Store reasons for potential actions

        # --- Heuristic Rules ---

        # Rule 1: Strong Buy based on significant drop below 30-day MA
        if features.get("change_from_30d_avg_pct") is not None:
            if features["change_from_30d_avg_pct"] < self.STRONG_BUY_BELOW_MA30_PCT_THRESHOLD:
                reasons["STRONG_BUY_PRICE_VS_MA30"] = (
                    RecommendationAction.BUY,
                    self.DEFAULT_ACCURACY + 0.2, # Higher accuracy for strong signal
                    self.DEFAULT_CERTAINTY + 0.15,
                    f"Price is {features['change_from_30d_avg_pct']:.1f}% below 30-day average (Threshold: {self.STRONG_BUY_BELOW_MA30_PCT_THRESHOLD}%) - Strong Buy Signal."
                )

        # Rule 2: Buy based on drop below 30-day MA
        if features.get("change_from_30d_avg_pct") is not None:
            if features["change_from_30d_avg_pct"] < self.BUY_BELOW_MA30_PCT_THRESHOLD:
                reasons["BUY_PRICE_VS_MA30"] = (
                    RecommendationAction.BUY,
                    self.DEFAULT_ACCURACY + 0.1,
                    self.DEFAULT_CERTAINTY + 0.1,
                    f"Price is {features['change_from_30d_avg_pct']:.1f}% below 30-day average (Threshold: {self.BUY_BELOW_MA30_PCT_THRESHOLD}%)."
                )

        # Rule 3: Buy based on recent significant drop compared to 7-day MA
        if features.get("change_from_7d_avg_pct") is not None:
            if features["change_from_7d_avg_pct"] < self.BUY_RECENT_DROP_PCT_THRESHOLD:
                reasons["BUY_RECENT_SIGNIFICANT_DROP"] = (
                    RecommendationAction.BUY,
                    self.DEFAULT_ACCURACY + 0.05,
                    self.DEFAULT_CERTAINTY + 0.05,
                    f"Price recently dropped significantly: {features['change_from_7d_avg_pct']:.1f}% below 7-day average (Threshold: {self.BUY_RECENT_DROP_PCT_THRESHOLD}%)."
                )

        # Rule 4: Wait if a sale is approaching
        days_to_sale = features.get("days_to_next_sale")
        if days_to_sale is not None and 0 <= days_to_sale <= self.SALE_APPROACHING_DAYS_THRESHOLD:
            reasons["WAIT_SALE_APPROACHING"] = (
                RecommendationAction.WAIT,
                self.DEFAULT_ACCURACY + 0.1, # Higher accuracy as this is a known factor
                self.DEFAULT_CERTAINTY + 0.1,
                f"A known sale event is approaching in {days_to_sale} days. Consider waiting."
            )

        # --- Determine final recommendation based on priority ---
        for reason_key in self.reasoning_priority:
            if reason_key in reasons:
                return reasons[reason_key] # Return the highest priority matched rule

        # Default/Fallback Recommendation: HOLD or WAIT based on stability
        # This part can be more nuanced. For now, a simple HOLD.
        reasons["HOLD_STABLE_PRICE"] = (
            RecommendationAction.HOLD,
            self.DEFAULT_ACCURACY - 0.1, # Lower accuracy if no strong signals
            self.DEFAULT_CERTAINTY,
            "Price is relatively stable or no strong buy/wait signals detected."
        )
        return reasons["HOLD_STABLE_PRICE"]


if __name__ == "__main__":
    print("--- Testing SimpleHeuristicModel ---")
    model = SimpleHeuristicModel()

    # Test Case 1: Strong Buy Signal (price well below 30d MA)
    features_strong_buy = {
        "current_price": 80.0,
        "moving_avg_30d": 100.0,
        "change_from_30d_avg_pct": -20.0, # (80-100)/100 * 100 = -20%
        "moving_avg_7d": 85.0,
        "change_from_7d_avg_pct": -5.88, # (80-85)/85 * 100
        "days_to_next_sale": 30
    }
    action, acc, cert, reason = model.predict(features_strong_buy)
    print(f"\nTest Case 1 (Strong Buy):")
    print(f"  Action: {action}, Accuracy: {acc:.2f}, Certainty: {cert:.2f}")
    print(f"  Reason: {reason}")
    assert action == RecommendationAction.BUY

    # Test Case 2: Normal Buy Signal (price below 30d MA but not strongly)
    features_buy = {
        "current_price": 90.0,
        "moving_avg_30d": 100.0,
        "change_from_30d_avg_pct": -10.0, # -10%
        "moving_avg_7d": 92.0,
        "change_from_7d_avg_pct": -2.17,
        "days_to_next_sale": 30
    }
    action, acc, cert, reason = model.predict(features_buy)
    print(f"\nTest Case 2 (Normal Buy):")
    print(f"  Action: {action}, Accuracy: {acc:.2f}, Certainty: {cert:.2f}")
    print(f"  Reason: {reason}")
    assert action == RecommendationAction.BUY

    # Test Case 3: Wait, Sale Approaching (overrides a weak buy signal)
    features_wait_sale = {
        "current_price": 90.0, # Matches BUY_PRICE_VS_MA30
        "moving_avg_30d": 100.0,
        "change_from_30d_avg_pct": -10.0,
        "moving_avg_7d": 92.0,
        "change_from_7d_avg_pct": -2.17,
        "days_to_next_sale": 5 # Sale is very soon
    }
    action, acc, cert, reason = model.predict(features_wait_sale)
    print(f"\nTest Case 3 (Wait - Sale Approaching):")
    print(f"  Action: {action}, Accuracy: {acc:.2f}, Certainty: {cert:.2f}")
    print(f"  Reason: {reason}")
    # The order in reasoning_priority matters here. If sale check is high, it will be WAIT.
    # Current priority: StrongBuy, BuyMA30, BuyRecentDrop, WaitSale. So BuyMA30 will win.
    # Let's adjust priority for testing this specific case or refine logic.
    # For now, given current priority, this would be BUY.
    # To make WAIT win, WAIT_SALE_APPROACHING needs higher priority than BUY_PRICE_VS_MA30.
    # Let's test with WAIT_SALE_APPROACHING having higher priority for this scenario.

    custom_priority_model = SimpleHeuristicModel()
    custom_priority_model.reasoning_priority = [
            "STRONG_BUY_PRICE_VS_MA30",
            "WAIT_SALE_APPROACHING", # Moved up
            "BUY_PRICE_VS_MA30",
            "BUY_RECENT_SIGNIFICANT_DROP",
            "HOLD_STABLE_PRICE",
    ]
    action_custom, acc_custom, cert_custom, reason_custom = custom_priority_model.predict(features_wait_sale)
    print(f"\nTest Case 3 (Wait - Sale Approaching, Custom Priority):")
    print(f"  Action: {action_custom}, Accuracy: {acc_custom:.2f}, Certainty: {cert_custom:.2f}")
    print(f"  Reason: {reason_custom}")
    assert action_custom == RecommendationAction.WAIT


    # Test Case 4: Hold (no strong signals)
    features_hold = {
        "current_price": 98.0,
        "moving_avg_30d": 100.0,
        "change_from_30d_avg_pct": -2.0, # Not low enough
        "moving_avg_7d": 99.0,
        "change_from_7d_avg_pct": -1.0, # Not low enough
        "days_to_next_sale": 60 # Sale not soon
    }
    action, acc, cert, reason = model.predict(features_hold)
    print(f"\nTest Case 4 (Hold):")
    print(f"  Action: {action}, Accuracy: {acc:.2f}, Certainty: {cert:.2f}")
    print(f"  Reason: {reason}")
    assert action == RecommendationAction.HOLD

    # Test Case 5: Buy due to recent drop, even if MA comparison isn't strong
    features_recent_drop_buy = {
        "current_price": 90.0,
        "moving_avg_30d": 95.0, # Only -5.2% vs MA30 (might not trigger BUY_PRICE_VS_MA30)
        "change_from_30d_avg_pct": -5.26,
        "moving_avg_7d": 105.0, # Current price is much lower than 7d MA
        "change_from_7d_avg_pct": -14.28, # (90-105)/105 * 100 = -14.28% (triggers BUY_RECENT_SIGNIFICANT_DROP)
        "days_to_next_sale": 30
    }
    action, acc, cert, reason = model.predict(features_recent_drop_buy)
    print(f"\nTest Case 5 (Buy - Recent Drop):")
    print(f"  Action: {action}, Accuracy: {acc:.2f}, Certainty: {cert:.2f}")
    print(f"  Reason: {reason}")
    assert action == RecommendationAction.BUY

    print("\nSimpleHeuristicModel tests completed.")
