from pantry_engine import add_item, process_deductions, inventory_sort, get_total_stock, inventory
from ai import scan_bill_with_ai
from datetime import date, timedelta

RECIPES = [
    {
        "name": "Tomato Onion Curry",
        "serves": 2,
        "ingredients": {
            "tomato": 0.4,
            "onion": 0.25,
            "garlic": 10,
            "green chili": 10,
            "salt": 0.01,
        },
    },
    {
        "name": "Paneer Bhurji",
        "serves": 2,
        "ingredients": {
            "paneer": 200,
            "onion": 0.2,
            "tomato": 0.2,
            "green chili": 5,
            "coriander leaf": 0.1,
            "salt": 0.01,
        },
    },
    {
        "name": "Masala Potato",
        "serves": 2,
        "ingredients": {
            "potato": 0.4,
            "onion": 0.15,
            "tomato": 0.1,
            "garlic": 10,
            "cumin seed": 5,
            "salt": 0.01,
        },
    },
    {
        "name": "Vegetable Soup",
        "serves": 2,
        "ingredients": {
            "carrot": 0.2,
            "tomato": 0.2,
            "cabbage": 0.1,
            "onion": 0.15,
            "garlic": 10,
            "salt": 0.01,
        },
    },
]


def display_inventory():
    if not inventory:
        print("Pantry is currently empty.")
        return

    print("\nPantry inventory:")
    for item in inventory:
        print(f" - {item['qty']} {item['unit']} {item['name']} (expires {item['expiry']})")


def add_item_prompt():
    name = input("Item name: ").strip()
    try:
        qty = float(input("Quantity: "))
    except ValueError:
        print("Please enter a valid numeric quantity.")
        return

    expiry = input("Expiry date (optional, e.g. 2026-05-20): ").strip() or None
    try:
        add_item(name, qty, raw_expiry=expiry)
        inventory_sort()
    except Exception as e:
        print(f"Failed to add item: {e}")


def upload_bill_prompt():
    image_path = input("Enter receipt image path: ").strip()
    if not image_path:
        print("No path entered.")
        return

    items = scan_bill_with_ai(image_path)
    if not items:
        print("No bill items were parsed from the image.")
        return

    print("Parsed bill items:")
    for item in items:
        name = item.get("name")
        qty = item.get("qty")
        if not name or qty is None:
            continue
        print(f" - {qty} x {name}")
        try:
            add_item(name, float(qty), price=0)
        except Exception as e:
            print(f"Could not add {name}: {e}")

    inventory_sort()
    print("Receipt items added to pantry.")


def scale_recipe(recipe, people):
    scale = people / recipe["serves"]
    return {name: qty * scale for name, qty in recipe["ingredients"].items()}


def can_make_recipe(scaled_ingredients):
    missing = {}
    for name, qty in scaled_ingredients.items():
        available = get_total_stock(name)
        if available < qty:
            missing[name] = {"required": qty, "available": available}
    return missing


def choose_recipe_for_people(people):
    index = 0
    while index < len(RECIPES):
        recipe = RECIPES[index]
        scaled = scale_recipe(recipe, people)

        print(f"\nSuggested recipe: {recipe['name']} for {people} people")
        for name, qty in scaled.items():
            print(f" - {qty:.2f} {name}")

        missing = can_make_recipe(scaled)
        if missing:
            print("You are missing these ingredients:")
            for name, values in missing.items():
                print(f" - {name}: required {values['required']:.2f}, available {values['available']:.2f}")

            answer = input("Type 'give me' to see another recipe, or 'no' to return to main menu: ").strip().lower()
            if "give me" in answer or "some" in answer or "other" in answer:
                index += 1
                continue
            return

        answer = input("Type 'ok' to use this recipe, or 'give me some this kind of thing' to see another recipe: ").strip().lower()
        if answer == "ok":
            process_deductions(scaled)
            inventory_sort()
            print("Ingredients deducted from pantry.")
            display_inventory()
            return

        if "give me" in answer or "some" in answer or "other" in answer:
            index += 1
            continue

        print("Please type 'ok' or ask for another recipe.")

    print("No more recipe suggestions available.")


def recipe_suggestion_prompt():
    try:
        people = int(input("Enter number of people: "))
    except ValueError:
        print("Please enter a valid number of people.")
        return

    choose_recipe_for_people(people)


def expiring_soon_prompt(days=3):
    cutoff = date.today() + timedelta(days=days)
    expiring_items = [item for item in inventory if item["expiry"] <= cutoff]

    if not expiring_items:
        print(f"No items expiring within the next {days} days.")
        return

    print(f"\nItems expiring in the next {days} days:")
    for item in expiring_items:
        print(f" - {item['name']}: {item['qty']} {item['unit']} (expires {item['expiry']})")


def main_menu():
    while True:
        print("\nSaffron\nNo need to worry about the pantry\n")
        print("1. Show pantry inventory")
        print("2. Add pantry item")
        print("3. Upload receipt and auto add")
        print("4. Suggest a recipe")
        print("5. Show items expiring in 3 days")
        print("0. Exit")

        choice = input("Select an option: ").strip()
        if choice == "1":
            display_inventory()
        elif choice == "2":
            add_item_prompt()
        elif choice == "3":
            upload_bill_prompt()
        elif choice == "4":
            recipe_suggestion_prompt()
        elif choice == "5":
            expiring_soon_prompt(3)
        elif choice == "0":
            print("Goodbye.")
            break
        else:
            print("Please select a valid option.")


def initialize_sample_pantry():
    add_item("tomato", 2, price=0)
    add_item("onion", 1, price=0)
    add_item("garlic", 100, price=0)
    add_item("green chili", 50, price=0)
    add_item("salt", 1, price=0)
    add_item("paneer", 250, price=0)
    add_item("coriander leaf", 1, price=0)
    add_item("potato", 2, price=0)
    add_item("carrot", 1, price=0)
    add_item("cabbage", 1, price=0)
    inventory_sort()


if __name__ == "__main__":
    initialize_sample_pantry()
    main_menu()
