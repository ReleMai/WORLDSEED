"""Read-only quantity quotes shared by market menus and their regression checks."""


def trade_total(sim, settlement_id, item_id, buy, amount):
    quote = getattr(sim, 'player_trade_total', None)
    if callable(quote):
        return quote(settlement_id, item_id, buy, amount)
    # Lightweight terminal fixtures and older adapters still expose unit quotes.
    return max(0, int(amount)) * max(1, sim.player_trade_price(settlement_id, item_id, buy))


def max_affordable_trade(sim, settlement_id, item_id, stock, copper):
    """Search cumulative instance prices; stack units need not share one price."""
    low, high = 0, min(max(0, int(stock)), max(0, int(copper)))
    while low < high:
        middle = (low + high + 1) // 2
        if trade_total(sim, settlement_id, item_id, True, middle) <= copper:
            low = middle
        else:
            high = middle - 1
    return low
