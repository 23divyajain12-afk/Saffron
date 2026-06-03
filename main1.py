from pantry_engine import add_item, process_deductions, inventory_sort, get_total_stock, inventory

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


def print_recipe_suggestion(recipe, people):
    scaled = scale_recipe(recipe, people)
    print(f"\nRecipe suggestion: {recipe['name']} for {people} people")
    print("Ingredients:")
    for name, qty in scaled.items():
        print(f" - {qty:.2f} of {name}")
    return scaled


def suggest_recipe_loop():
    print("Welcome to the Saffron recipe suggester.")
    people = input("Enter number of people: ")
    try:
        people_count = int(people)
    except ValueError:
        print("Please enter a valid integer for people.")
        return

    suggestions = RECIPES.copy()
    suggestion_index = 0

    while suggestions:
        recipe = suggestions[suggestion_index % len(suggestions)]
        scaled = print_recipe_suggestion(recipe, people_count)
        missing = can_make_recipe(scaled)

        if missing:
            print("You do not have enough of these ingredients in the pantry:")
            for name, values in missing.items():
                print(f" - {name}: required {values['required']:.2f}, available {values['available']:.2f}")
            answer = input("Would you like another recipe? (yes/no): ")
            if answer.strip().lower() in {"yes", "y", "give me", "give me some", "some", "other"}:
                suggestion_index += 1
                continue
            break

        answer = input("If you want this recipe, type ok. To see another recipe, type 'give me some this kind of thing'.\nYour answer: ")
        normalized = answer.strip().lower()

        if normalized == "ok":
            process_deductions(scaled)
            inventory_sort()
            print("Ingredients have been deducted from the pantry.")
            print("Updated pantry: ")
            for item in inventory:
                print(f" - {item['qty']} {item['unit']} {item['name']} (expires {item['expiry']})")
            follow_up = input("Do you want another recipe suggestion? (yes/no): ")
            if follow_up.strip().lower() in {"yes", "y", "give me", "give me some", "some", "other"}:
                suggestion_index += 1
                continue
            break

        if any(keyword in normalized for keyword in ["give me", "some", "other", "again"]):
            suggestion_index += 1
            continue

        print("I did not understand that response. Please type 'ok' or ask for another recipe.")

    print("No more recipe suggestions available.")


def main():
    print("Setting up pantry example items...")
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
    suggest_recipe_loop()


if __name__ == "__main__":
    main()
