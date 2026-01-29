import asyncio
import itertools
import random
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

STATIC_DIR = Path(__file__).parent / "static"

# 确保目录存在，如果不存在则创建
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

STARTING_STACK = 1000
SMALL_BLIND = 10
BIG_BLIND = 20
PLAY_PHASES = ["preflop", "flop", "turn", "river"]
SUITS = ["S", "H", "D", "C"]
RANKS = list(range(2, 15))
RANK_DISPLAY = {11: "J", 12: "Q", 13: "K", 14: "A"}
HAND_NAMES = {
    8: "Straight Flush",
    7: "Four of a Kind",
    6: "Full House",
    5: "Flush",
    4: "Straight",
    3: "Three of a Kind",
    2: "Two Pair",
    1: "One Pair",
    0: "High Card",
}

# AI 机器人名称和风格
BOT_NAMES = ["Alex", "Sam", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Quinn"]
BOT_STYLES = ["保守", "激进", "平衡"]


def rank_to_label(value: int) -> str:
    return RANK_DISPLAY.get(value, str(value))


def card_to_label(card: Dict[str, int]) -> str:
    return f"{rank_to_label(card['rank'])}{card['suit']}"


def build_deck() -> List[Dict[str, int]]:
    return [{"rank": rank, "suit": suit} for suit in SUITS for rank in RANKS]


class AIPlayer(Player):
    """AI 机器人玩家类"""

    def __init__(self, player_id: str, name: str, style: str = "平衡"):
        super().__init__(player_id, name)
        self.style = style  # 保守, 激进, 平衡
        self.action_timer = None
        self.thinking = False

    def decide_action(self, table_state: Dict) -> str:
        """根据游戏状态决定行动"""
        if self.thinking:
            return None

        to_call = table_state.get("viewerCallAmount", 0)
        pot = table_state.get("pot", 0)
        current_bet = table_state.get("currentBet", 0)
        my_chips = self.chips
        my_street_bet = self.street_bet

        self.thinking = True

        # 简单 AI 决策逻辑
        try:
            action = self._make_decision(to_call, pot, current_bet, my_chips, my_street_bet)
        except Exception:
            action = "fold"

        self.thinking = False
        return action

    def _make_decision(self, to_call: int, pot: int, current_bet: int,
                    my_chips: int, my_street_bet: int) -> str:
        """核心决策逻辑"""
        # 检查手牌强度（简化版）
        hand_strength = self._evaluate_hand_strength()

        if to_call == 0:
            # 可以过牌
            if hand_strength > 0.6 and random.random() < 0.4:
                return self._bet_action(my_chips, current_bet, pot)
            return "check"

        if to_call > my_chips:
            # 需要全压
            if hand_strength > 0.5:
                return "call"
            return random.choice(["call", "fold"])

        # 需要跟注
        call_ratio = to_call / (my_chips + my_street_bet) if my_chips + my_street_bet > 0 else 1

        if hand_strength > 0.7:
            # 强牌
            if call_ratio < 0.3:
                return self._raise_action(my_chips, my_street_bet, current_bet)
            return "call"
        elif hand_strength > 0.4:
            # 中等牌
            if call_ratio < 0.2 and random.random() < 0.5:
                return self._raise_action(my_chips, my_street_bet, current_bet)
            return random.choice(["call", "fold"] if random.random() < 0.3 else "call")
        else:
            # 弱牌
            if call_ratio > 0.3 and self.style == "激进":
                return self._raise_action(my_chips, my_street_bet, current_bet)
            if self.style == "保守":
                return "fold" if to_call > pot * 0.2 else "call"
            return random.choice(["call", "fold"]) if random.random() < 0.4 else "call"

    def _bet_action(self, my_chips: int, my_street_bet: int, current_bet: int) -> str:
        """决定下注金额"""
        if self.style == "保守":
            bet_amount = min(my_chips, current_bet * 2 if current_bet > 0 else self.big_blind_amount)
        elif self.style == "激进":
            bet_amount = min(my_chips, max(current_bet * 3, pot // 2))
        else:  # 平衡
            bet_amount = min(my_chips, max(current_bet * 2.5, pot // 3))
        self.pending_bet = bet_amount
        return "bet"

    def _raise_action(self, my_chips: int, my_street_bet: int, current_bet: int) -> str:
        """决定加注金额"""
        min_raise = current_bet + self.big_blind_amount
        if self.style == "保守":
            raise_amount = min(my_chips - my_street_bet, min_raise * 1.5)
        elif self.style == "激进":
            raise_amount = min(my_chips - my_street_bet, current_bet * 3)
        else:  # 平衡
            raise_amount = min(my_chips - my_street_bet, min_raise * 2)
        self.pending_bet = my_street_bet + raise_amount
        return "raise"

    def _evaluate_hand_strength(self) -> float:
        """评估手牌强度（简化版）"""
        if not self.cards or len(self.cards) < 2:
            return 0.3

        # 检查高牌
        high_cards = sum(1 for c in self.cards if c["rank"] >= 11)
        ranks = [c["rank"] for c in self.cards]

        # 对子
        pairs = len([r for r in set(ranks) if ranks.count(r) >= 2])
        # 同花
        same_suit = len(set(c["suit"] for c in self.cards)) == 2

        strength = 0.3
        if high_cards >= 1:
            strength += 0.15
        if pairs >= 1:
            strength += 0.2 * pairs
        if same_suit:
            strength += 0.1

        return min(strength, 0.9)

    def reset_for_round(self):
        super().reset_for_round()
        self.thinking = False
        self.pending_bet = None


class Player:
    def __init__(self, player_id: str, name: str):
        self.id = player_id
        self.name = name
        self.cards: List[Dict[str, int]] = []
        self.status = "waiting"  # waiting, active, folded, all_in, busted
        self.chips = STARTING_STACK
        self.street_bet = 0
        self.round_contrib = 0
        self.last_action: Optional[str] = None
        self.is_dealer = False
        self.is_small_blind = False
        self.is_big_blind = False

    def reset_for_round(self):
        self.cards = []
        self.street_bet = 0
        self.round_contrib = 0
        self.last_action = None
        self.is_small_blind = False
        self.is_big_blind = False
        self.is_dealer = False
        if self.chips <= 0:
            self.status = "busted"
        else:
            self.status = "active"


class PokerTable:
    def __init__(self):
        self.players: List[Player] = []
        self.host_id: Optional[str] = None
        self.phase = "waiting"
        self.board: List[Dict[str, int]] = []
        self.deck: List[Dict[str, int]] = []
        self.current_index: Optional[int] = None
        self.winners: List[Dict[str, str]] = []
        self.pot = 0
        self.current_bet = 0
        self.min_raise = BIG_BLIND
        self.awaiting_response: Set[str] = set()
        self.dealer_position: Optional[int] = None
        self.small_blind_amount = SMALL_BLIND
        self.big_blind_amount = BIG_BLIND
        self.dealer_id: Optional[str] = None
        self.small_blind_id: Optional[str] = None
        self.big_blind_id: Optional[str] = None
        self.auto_bots: List[AIPlayer] = []
        self.auto_play_enabled = False

    def add_player(self, name: str, is_bot: bool = False) -> Player:
        if is_bot:
            bot_names_used = [p.name for p in self.players if isinstance(p, AIPlayer)]
            available_names = [n for n in BOT_NAMES if n not in bot_names_used]
            name = random.choice(available_names) if available_names else name
            style = random.choice(BOT_STYLES)
            player = AIPlayer(str(uuid.uuid4()), name, style)
        else:
            player = Player(str(uuid.uuid4()), name)
        self.players.append(player)
        if not self.host_id:
            self.host_id = player.id
        return player

    def remove_player(self, player_id: str):
        removed_index = None
        for idx, player in enumerate(self.players):
            if player.id == player_id:
                removed_index = idx
                break
        if removed_index is None:
            return
        del self.players[removed_index]
        if self.host_id == player_id:
            self.host_id = self.players[0].id if self.players else None
        if self.dealer_position is not None:
            if removed_index < self.dealer_position:
                self.dealer_position -= 1
            elif removed_index == self.dealer_position:
                self.dealer_position = None
        if not self.players:
            self.reset_table()
            return
        self._sanitize_current_index()
        if self.phase in PLAY_PHASES and self.current_index is None:
            self.finish_with_remaining()

    def reset_table(self):
        self.phase = "waiting"
        self.board = []
        self.deck = []
        self.current_index = None
        self.winners = []
        self.pot = 0
        self.current_bet = 0
        self.min_raise = BIG_BLIND
        self.awaiting_response.clear()
        self.dealer_id = None
        self.small_blind_id = None
        self.big_blind_id = None
        if not self.players:
            self.dealer_position = None

    def _sanitize_current_index(self):
        if self.current_index is None:
            return
        if not self.players:
            self.current_index = None
            return
        self.current_index %= len(self.players)
        current = self.players[self.current_index]
        if current.status != "active":
            self.current_index = self._first_active_index()

    def _eligible_players(self) -> List[Player]:
        return [p for p in self.players if p.chips > 0]

    def _player_by_id(self, player_id: str) -> Optional[Player]:
        for player in self.players:
            if player.id == player_id:
                return player
        return None

    def start_round(self, requested_by: str):
        if requested_by != self.host_id:
            raise ValueError("Only the host can start a round")
        funded = self._eligible_players()
        if len(funded) < 2:
            raise ValueError("Need at least two players with chips")
        if self.phase in PLAY_PHASES:
            raise ValueError("Round already in progress")

        self.phase = "preflop"
        self.board = []
        self.deck = build_deck()
        random.shuffle(self.deck)
        self.winners = []
        self.pot = 0
        self.current_bet = 0
        self.min_raise = self.big_blind_amount
        self.awaiting_response = set()

        for player in self.players:
            player.reset_for_round()

        self._assign_positions()
        self._deal_private_cards()
        self._post_blinds()

        self.awaiting_response = {p.id for p in self.players if p.status == "active"}
        self.current_index = self._next_index(self.big_blind_id)
        if self.current_index is None:
            self.current_index = self._first_active_index()

    def _assign_positions(self):
        if not self.players:
            return
        start = self.dealer_position if self.dealer_position is not None else -1
        self.dealer_position = self._next_player_position(start)
        if self.dealer_position is None:
            raise ValueError("No dealer available")
        small_blind_pos = self._next_player_position(self.dealer_position)
        big_blind_pos = self._next_player_position(small_blind_pos)
        self.dealer_id = self.players[self.dealer_position].id if self.dealer_position is not None else None
        self.small_blind_id = self.players[small_blind_pos].id if small_blind_pos is not None else None
        self.big_blind_id = self.players[big_blind_pos].id if big_blind_pos is not None else None
        for idx, player in enumerate(self.players):
            player.is_dealer = idx == self.dealer_position
            player.is_small_blind = self.small_blind_id == player.id
            player.is_big_blind = self.big_blind_id == player.id

    def _deal_private_cards(self):
        active = [p for p in self.players if p.status == "active"]
        for _ in range(2):
            for player in active:
                player.cards.append(self.deck.pop())

    def _post_blinds(self):
        if self.small_blind_id:
            self._commit_chips(self.small_blind_id, self.small_blind_amount, label="小盲")
        if self.big_blind_id:
            self._commit_chips(self.big_blind_id, self.big_blind_amount, label="大盲")
            big_blind_player = self._player_by_id(self.big_blind_id)
            if big_blind_player:
                self.current_bet = big_blind_player.street_bet
                self.min_raise = self.big_blind_amount

    def _commit_chips(self, player_id: str, amount: int, label: Optional[str] = None):
        player = self._player_by_id(player_id)
        if not player or player.status not in {"active", "waiting"}:
            return
        to_pay = min(amount, player.chips)
        if to_pay <= 0:
            return
        player.chips -= to_pay
        player.street_bet += to_pay
        player.round_contrib += to_pay
        self.pot += to_pay
        if label:
            player.last_action = label
        if player.chips == 0:
            player.status = "all_in"

    def _next_player_position(self, start_index: Optional[int]) -> Optional[int]:
        if not self.players:
            return None
        total = len(self.players)
        idx = 0 if start_index is None else (start_index + 1) % total
        for _ in range(total):
            player = self.players[idx]
            if player.chips > 0:
                return idx
            idx = (idx + 1) % total
        return None

    def _next_index(self, player_id: Optional[str]) -> Optional[int]:
        if player_id is None or not self.players:
            return self._first_active_index()
        start = None
        for idx, player in enumerate(self.players):
            if player.id == player_id:
                start = idx
                break
        if start is None:
            return self._first_active_index()
        idx = (start + 1) % len(self.players)
        for _ in range(len(self.players)):
            if self.players[idx].status == "active":
                return idx
            idx = (idx + 1) % len(self.players)
        return None

    def _first_active_index(self) -> Optional[int]:
        for idx, player in enumerate(self.players):
            if player.status == "active":
                return idx
        return None

    def get_current_player(self) -> Optional[Player]:
        if self.current_index is None or not self.players:
            return None
        current = self.players[self.current_index]
        if current.status != "active":
            self.current_index = self._first_active_index()
            if self.current_index is None:
                return None
            current = self.players[self.current_index]
        return current

    def handle_action(self, player_id: str, action: str, amount: Optional[int] = None):
        if self.phase not in PLAY_PHASES:
            raise ValueError("Round is not active")
        player = self._player_by_id(player_id)
        if not player or player.status != "active":
            raise ValueError("You cannot act right now")
        current = self.get_current_player()
        if not current or current.id != player_id:
            raise ValueError("Not your turn")

        if action == "fold":
            self._fold(player)
        elif action == "check":
            self._check(player)
        elif action == "call":
            self._call(player)
        elif action == "bet":
            self._bet(player, amount)
        elif action == "raise":
            self._raise(player, amount)
        else:
            raise ValueError("Unsupported action")

        self._after_player_action(player)

    def _fold(self, player: Player):
        player.status = "folded"
        player.last_action = "弃牌"
        self.awaiting_response.discard(player.id)

    def _check(self, player: Player):
        if player.street_bet != self.current_bet:
            raise ValueError("Cannot check when facing a bet")
        player.last_action = "过牌"
        self.awaiting_response.discard(player.id)

    def _call(self, player: Player):
        to_call = self.current_bet - player.street_bet
        if to_call <= 0:
            raise ValueError("Nothing to call")
        payment = min(to_call, player.chips)
        self._commit_chips(player.id, payment)
        player.last_action = "跟注" if payment == to_call else "全压跟注"
        self.awaiting_response.discard(player.id)

    def _bet(self, player: Player, amount: Optional[int]):
        if self.current_bet != 0:
            raise ValueError("Betting already opened")
        size = self._validate_amount(amount)
        max_total = player.street_bet + player.chips
        if size < self.big_blind_amount and size != max_total:
            raise ValueError(f"Bet must be at least {self.big_blind_amount}，或直接全压")
        target = min(size, max_total)
        diff = target - player.street_bet
        if diff <= 0:
            raise ValueError("Bet must increase your wager")
        self._commit_chips(player.id, diff)
        self.current_bet = player.street_bet
        self.min_raise = max(target, self.big_blind_amount)
        action_label = "全压" if player.chips == 0 else "下注"
        player.last_action = f"{action_label} {target}"
        self._reset_awaiting(player)

    def _raise(self, player: Player, amount: Optional[int]):
        if self.current_bet == 0:
            raise ValueError("You must bet first")
        target = self._validate_amount(amount)
        max_total = player.street_bet + player.chips
        if target > max_total:
            target = max_total
        if target <= self.current_bet:
            raise ValueError("Raise must exceed current bet")
        diff = target - player.street_bet
        if diff <= 0:
            raise ValueError("Raise must increase your wager")
        increment = target - self.current_bet
        if increment < self.min_raise and target != max_total:
            raise ValueError(f"Raise must increase by at least {self.min_raise}")
        self._commit_chips(player.id, diff)
        self.current_bet = player.street_bet
        if increment >= self.min_raise:
            self.min_raise = increment
        action_label = "全压加注" if player.chips == 0 else "加注到"
        player.last_action = f"{action_label} {target}"
        self._reset_awaiting(player)

    def _validate_amount(self, amount: Optional[int]) -> int:
        if amount is None:
            raise ValueError("Amount required")
        try:
            size = int(amount)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid amount") from exc
        if size <= 0:
            raise ValueError("Amount must be positive")
        return size

    def _reset_awaiting(self, aggressor: Player):
        self.awaiting_response = {p.id for p in self.players if p.status == "active" and p.id != aggressor.id}

    def _after_player_action(self, acting_player: Player):
        self._cleanup_inactive_players()
        active_or_all_in = [p for p in self.players if p.status in {"active", "all_in"}]
        if len(active_or_all_in) <= 1:
            self.finish_with_remaining()
            return
        if not self.awaiting_response:
            # everyone responded, move to next phase or showdown
            self.advance_phase()
            return
        self.advance_turn()
        # 如果启用自动游戏且当前玩家是AI，触发AI行动
        if self.auto_play_enabled:
            self._trigger_ai_action()

    def _cleanup_inactive_players(self):
        for player in self.players:
            if player.status == "active" and player.chips == 0:
                player.status = "all_in"
                self.awaiting_response.discard(player.id)
            elif player.status != "active":
                self.awaiting_response.discard(player.id)

    def advance_turn(self):
        if not self.players:
            self.current_index = None
            return
        if self.current_index is None:
            self.current_index = self._first_active_index()
            return
        for _ in range(len(self.players)):
            self.current_index = (self.current_index + 1) % len(self.players)
            if self.players[self.current_index].status == "active":
                return
        self.current_index = None

    def advance_phase(self):
        if self.phase not in PLAY_PHASES:
            return
        if self.phase == "preflop":
            self._burn()
            self.board.extend([self.deck.pop(), self.deck.pop(), self.deck.pop()])
            self.phase = "flop"
        elif self.phase == "flop":
            self._burn()
            self.board.append(self.deck.pop())
            self.phase = "turn"
        elif self.phase == "turn":
            self._burn()
            self.board.append(self.deck.pop())
            self.phase = "river"
        elif self.phase == "river":
            self.phase = "showdown"
            self.resolve_showdown()
            return

        self.current_bet = 0
        self.min_raise = self.big_blind_amount
        for player in self.players:
            player.street_bet = 0
            if player.status == "active":
                player.last_action = None
        self.awaiting_response = {p.id for p in self.players if p.status == "active"}
        self.current_index = self._next_index(self.dealer_id)
        if self.current_index is None:
            self.current_index = self._first_active_index()

    def _burn(self):
        if self.deck:
            self.deck.pop()

    def finish_with_remaining(self):
        survivors = [p for p in self.players if p.status in {"active", "all_in"}]
        if not survivors:
            self.reset_table()
            return
        winner = survivors[0]
        winner.chips += self.pot
        self.winners = [
            {
                "playerId": winner.id,
                "name": winner.name,
                "handName": "Last Player Standing",
                "hand": [card_to_label(card) for card in winner.cards],
                "payout": self.pot,
            }
        ]
        self.pot = 0
        self.phase = "showdown"
        self.current_index = None
        self.awaiting_response.clear()
        self._mark_post_round_states()

    def resolve_showdown(self):
        contenders = [p for p in self.players if p.status in {"active", "all_in"}]
        if not contenders:
            self.reset_table()
            return
        scored = []
        for player in contenders:
            score, best_hand = evaluate_best_hand(player.cards + self.board)
            scored.append((score, player, best_hand))
        scored.sort(key=lambda item: item[0], reverse=True)
        top_score = scored[0][0]
        winners = [item for item in scored if item[0] == top_score]
        share = self.pot // len(winners)
        remainder = self.pot % len(winners)
        payouts = []
        for idx, (score, player, best_hand) in enumerate(winners):
            extra = 1 if idx < remainder else 0
            payout = share + extra
            player.chips += payout
            payouts.append(
                {
                    "playerId": player.id,
                    "name": player.name,
                    "handName": HAND_NAMES[top_score[0]],
                    "hand": [card_to_label(card) for card in best_hand],
                    "payout": payout,
                }
            )
        self.winners = payouts
        self.pot = 0
        self.current_index = None
        self.awaiting_response.clear()
        self._mark_post_round_states()

    def _mark_post_round_states(self):
        for player in self.players:
            if player.chips <= 0:
                player.status = "busted"
            elif player.status not in {"waiting", "busted"}:
                player.status = "waiting"
            player.street_bet = 0
            player.round_contrib = 0

    def add_bot_player(self, count: int = 1):
        """添加指定数量的 AI 机器人玩家"""
        added = []
        for _ in range(count):
            player = self.add_player("Bot", is_bot=True)
            self.auto_bots.append(player)
            added.append(player)
        return added

    def remove_all_bots(self):
        """移除所有 AI 机器人"""
        to_remove = [bot.id for bot in self.auto_bots]
        for bot_id in to_remove:
            self.remove_player(bot_id)
        self.auto_bots.clear()

    def toggle_auto_play(self, enabled: bool):
        """切换自动游戏模式"""
        self.auto_play_enabled = enabled

    def _trigger_ai_action(self):
        """触发 AI 行动"""
        if not self.auto_play_enabled:
            return

        current = self.get_current_player()
        if not current or not isinstance(current, AIPlayer):
            return

        # 如果当前等待的是 AI，让它行动
        if current.id in self.awaiting_response:
            table_state = self.state_for(current.id)
            action = current.decide_action(table_state)

            if action:
                amount = None
                if action in ["bet", "raise"]:
                    if hasattr(current, "pending_bet") and current.pending_bet:
                        amount = current.pending_bet

                try:
                    self.handle_action(current.id, action, amount)
                except ValueError:
                    pass

    def available_actions_for(self, viewer_id: Optional[str]) -> List[str]:
        viewer = self._player_by_id(viewer_id) if viewer_id else None
        if not viewer or viewer.status != "active" or self.phase not in PLAY_PHASES:
            return []
        current = self.get_current_player()
        if not current or current.id != viewer.id:
            return []
        actions = ["fold"]
        if self.current_bet == 0:
            actions.append("check")
            if viewer.chips > 0:
                actions.append("bet")
            return actions
        if viewer.street_bet == self.current_bet:
            if viewer.chips + viewer.street_bet > self.current_bet:
                actions.append("raise")
            return actions
        if viewer.chips > 0:
            actions.append("call")
            if viewer.chips + viewer.street_bet > self.current_bet:
                actions.append("raise")
        return actions

    def state_for(self, viewer_id: Optional[str]) -> Dict:
        def visible_cards(player: Player) -> List[Optional[str]]:
            show_cards = self.phase == "showdown" or player.id == viewer_id
            return [card_to_label(card) if show_cards else None for card in player.cards]

        current = self.get_current_player()
        viewer = self._player_by_id(viewer_id) if viewer_id else None
        viewer_call = 0
        if viewer and self.phase in PLAY_PHASES and viewer.status in {"active", "all_in"}:
            viewer_call = max(0, self.current_bet - viewer.street_bet)
        return {
            "phase": self.phase,
            "board": [card_to_label(card) for card in self.board],
            "players": [
                {
                    "id": player.id,
                    "name": player.name,
                    "status": player.status,
                    "cards": visible_cards(player),
                    "isHost": player.id == self.host_id,
                    "chips": player.chips,
                    "streetBet": player.street_bet,
                    "lastAction": player.last_action,
                    "isDealer": player.is_dealer,
                    "isSmallBlind": player.is_small_blind,
                    "isBigBlind": player.is_big_blind,
                }
                for player in self.players
            ],
            "currentPlayerId": current.id if current else None,
            "hostId": self.host_id,
            "winners": self.winners,
            "viewerId": viewer_id,
            "canStart": viewer_id == self.host_id and len(self._eligible_players()) >= 2 and self.phase in {"waiting", "showdown"},
            "deckRemaining": len(self.deck),
            "pot": self.pot,
            "currentBet": self.current_bet,
            "minRaise": self.min_raise,
            "blinds": {"small": self.small_blind_amount, "big": self.big_blind_amount},
            "availableActions": self.available_actions_for(viewer_id),
            "viewerCallAmount": viewer_call,
            "dealerId": self.dealer_id,
            "smallBlindId": self.small_blind_id,
            "bigBlindId": self.big_blind_id,
        }


def evaluate_best_hand(cards: List[Dict[str, int]]):
    best_score = None
    best_hand = None
    for combo in itertools.combinations(cards, 5):
        score = score_five_card_hand(combo)
        if best_score is None or score > best_score:
            best_score = score
            best_hand = combo
    return best_score, best_hand


def score_five_card_hand(cards: tuple):
    ranks = sorted([card["rank"] for card in cards], reverse=True)
    suits = [card["suit"] for card in cards]
    counts: Dict[int, int] = {}
    for rank in ranks:
        counts[rank] = counts.get(rank, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    is_flush = len(set(suits)) == 1
    is_straight, top = check_straight(ranks)

    if is_straight and is_flush:
        return (8, [top])
    if ordered[0][1] == 4:
        kicker = max(rank for rank in ranks if rank != ordered[0][0])
        return (7, [ordered[0][0], kicker])
    if ordered[0][1] == 3 and ordered[1][1] == 2:
        return (6, [ordered[0][0], ordered[1][0]])
    if is_flush:
        return (5, ranks)
    if is_straight:
        return (4, [top])
    if ordered[0][1] == 3:
        kickers = sorted([rank for rank in ranks if rank != ordered[0][0]], reverse=True)
        return (3, [ordered[0][0]] + kickers)
    if ordered[0][1] == 2 and ordered[1][1] == 2:
        pair_ranks = sorted([ordered[0][0], ordered[1][0]], reverse=True)
        kicker = max(rank for rank in ranks if rank not in pair_ranks)
        return (2, pair_ranks + [kicker])
    if ordered[0][1] == 2:
        kickers = sorted([rank for rank in ranks if rank != ordered[0][0]], reverse=True)
        return (1, [ordered[0][0]] + kickers)
    return (0, ranks)


def check_straight(ranks: List[int]):
    unique = sorted(set(ranks), reverse=True)
    if len(unique) < 5:
        if set([14, 5, 4, 3, 2]).issubset(set(ranks)):
            return True, 5
        return False, None
    for i in range(len(unique) - 4):
        window = unique[i : i + 5]
        if window[0] - window[-1] == 4:
            return True, window[0]
    if set([14, 5, 4, 3, 2]).issubset(set(unique)):
        return True, 5
    return False, None


class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

    def attach(self, player_id: str, websocket: WebSocket):
        self.active[player_id] = websocket

    def detach(self, player_id: Optional[str]):
        if player_id and player_id in self.active:
            del self.active[player_id]

    async def send_personal(self, player_id: str, message: Dict):
        socket = self.active.get(player_id)
        if socket:
            await socket.send_json(message)


table = PokerTable()
manager = ConnectionManager()
table_lock = asyncio.Lock()


async def broadcast_state():
    stale: List[str] = []
    for player_id, socket in list(manager.active.items()):
        try:
            await socket.send_json({"type": "state", "payload": table.state_for(player_id)})
        except Exception:
            stale.append(player_id)
    for player_id in stale:
        manager.detach(player_id)
        table.remove_player(player_id)


@app.get("/")
async def index():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    player_id: Optional[str] = None
    ai_task: Optional[asyncio.Task] = None
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            error: Optional[str] = None
            async with table_lock:
                try:
                    if msg_type == "join":
                        name = data.get("name", "Player")
                        player = table.add_player(name)
                        player_id = player.id
                        manager.attach(player_id, websocket)
                        await manager.send_personal(
                            player_id, {"type": "joined", "payload": {"playerId": player_id}}
                        )
                    elif msg_type == "start_round" and player_id:
                        table.start_round(player_id)
                        # 如果已启用自动游戏且有机器人，自动开始
                        if table.auto_play_enabled and table.auto_bots:
                            ai_task = asyncio.create_task(_ai_auto_play())
                    elif msg_type == "action" and player_id:
                        table.handle_action(player_id, data.get("action"), data.get("amount"))
                    elif msg_type == "add_bot":
                        count = data.get("count", 1)
                        bots = table.add_bot_player(count)
                        await websocket.send_json({
                            "type": "bots_added",
                            "payload": [{"id": b.id, "name": b.name, "style": b.style} for b in bots]
                        })
                    elif msg_type == "remove_bots":
                        table.remove_all_bots()
                        await websocket.send_json({"type": "bots_removed", "payload": {}})
                    elif msg_type == "toggle_auto_play":
                        enabled = data.get("enabled", False)
                        table.toggle_auto_play(enabled)
                        if enabled and table.auto_bots:
                            if ai_task and not ai_task.done():
                                ai_task.cancel()
                            ai_task = asyncio.create_task(_ai_auto_play())
                        elif ai_task:
                            ai_task.cancel()
                            ai_task = None
                except ValueError as exc:
                    error = str(exc)
            await broadcast_state()
            if error:
                await websocket.send_json({"type": "error", "message": error})
    except WebSocketDisconnect:
        pass
    finally:
        async with table_lock:
            manager.detach(player_id)
            if player_id:
                table.remove_player(player_id)
            if ai_task and not ai_task.done():
                ai_task.cancel()
        await broadcast_state()


async def _ai_auto_play():
    """AI 自动游戏循环"""
    while table.auto_play_enabled and table.auto_bots and table.phase in PLAY_PHASES:
        current = table.get_current_player()
        if not current or not isinstance(current, AIPlayer):
            await asyncio.sleep(1)
            continue

        if current.id not in table.awaiting_response:
            await asyncio.sleep(0.5)
            continue

        table_state = table.state_for(current.id)
        action = current.decide_action(table_state)

        if action:
            amount = None
            if action in ["bet", "raise"]:
                if hasattr(current, "pending_bet") and current.pending_bet:
                    amount = current.pending_bet

            try:
                table.handle_action(current.id, action, amount)
            except ValueError:
                pass

        await broadcast_state()
        await asyncio.sleep(1)


@app.get("/health")
async def health():
    return {"status": "ok"}
