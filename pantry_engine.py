from utils import get_singular_name, load_constants, parse_expiry, calculate_expiry_date

constants = load_constants()
inventory = []
stock_hash_map = {}


def add_item(name, qty, raw_expiry=None, price=0):
    clean_name = get_singular_name(name)
    try:
        if raw_expiry:
            expiry_date = parse_expiry(raw_expiry)
        else:
            expiry_date = calculate_expiry_date(clean_name, constants)

        unit = constants.get(clean_name, {}).get("unit", "units")
        item = {
            "name": clean_name,
            "expiry": expiry_date,
            "qty": qty,
            "unit": unit,
            "price": price,
        }

        inventory.append(item)
        stock_hash_map[clean_name] = stock_hash_map.get(clean_name, 0) + qty
        print(f"Added {qty} {unit} of {clean_name} (Expires: {expiry_date})")
    except Exception as e:
        print(f"Error adding {name}: {e}")


def inventory_sort():
    inventory.sort(key=lambda item: item["expiry"])


def get_total_stock(item_name):
    target = get_singular_name(item_name)
    return sum(it.get("qty", 0) for it in inventory if it.get("name") == target)

def consume_item(name, amount_to_use):
    target = get_singular_name(name)
    remaining_to_deduct = amount_to_use

    if stock_hash_map.get(target, 0) < amount_to_use:
        print(f"Warning: Not enough {target} in stock!")
        return

    stock_hash_map[target] -= amount_to_use
    inventory_sort()

    i = 0
    while remaining_to_deduct > 0 and i < len(inventory):
        batch = inventory[i]
        if batch["name"] != target:
            i += 1
            continue

        batch_qty = batch["qty"]
        if batch_qty <= remaining_to_deduct:
            remaining_to_deduct -= batch_qty
            print(f"Emptying batch expiring {batch['expiry']}")
            inventory.pop(i)
        else:
            batch["qty"] -= remaining_to_deduct
            remaining_to_deduct = 0
            print(f"Subtracted from batch expiring {batch['expiry']}. Remaining in batch: {batch['qty']}")

    if remaining_to_deduct > 0:
        print(f"Could not deduct the full amount for {target}. Remaining: {remaining_to_deduct}")
    else:
        print(f"Successfully used {amount_to_use} of {target}.")


def process_deductions(recipe_ingredients):
    print("\n--- Inventory Update Log ---")
    for item_name, quantity in recipe_ingredients.items():
        consume_item(item_name, quantity)

    inventory_sort()
    print("--- Pantry synchronized with Recipe ---")
