points = 55  # preset (no input() in browser)
if points < 100:
    points *= 1.1
    print("Your bonus is 10 %")

elif points >= 100:
    points *= 1.15
    print("Your bonus is 15 %")

print("You now have", points, "points")
