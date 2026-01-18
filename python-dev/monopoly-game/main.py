import numpy as np

position_mapping  = {
    0: {"name": "Go", "type": "Corner", "colour": None},
    1: {"name": "Old Kent Road", "type": "Property", "colour": "Brown"},
    2: {"name": "Community Chest", "type": "Community Chest", "colour": None},
    3: {"name": "Whitechapel Road", "type": "Property", "colour": "Brown"},
    4: {"name": "Income Tax", "type": "Tax", "colour": None},
    5: {"name": "King's Cross Station", "type": "Station", "colour": None},
    6: {"name": "The Angel Islington", "type": "Property", "colour": "Light Blue"},
    7: {"name": "Chance", "type": "Chance", "colour": None},
    8: {"name": "Euston Road", "type": "Property", "colour": "Light Blue"},
    9: {"name": "Pentonville Road", "type": "Property", "colour": "Light Blue"},
    10: {"name": "Jail", "type": "Corner", "colour": None},
    11: {"name": "Pall Mall", "type": "Property", "colour": "Pink"},
    12: {"name": "Electric Company", "type": "Utility", "colour": None},
    13: {"name": "Whitehall", "type": "Property", "colour": "Pink"},
    14: {"name": "Northumberland Avenue", "type": "Property", "colour": "Pink"},
    15: {"name": "Marylebone Station", "type": "Station", "colour": None},
    16: {"name": "Bow Street", "type": "Property", "colour": "Orange"},
    17: {"name": "Community Chest", "type": "Community Chest", "colour": None},
    18: {"name": "Marlborough Street", "type": "Property", "colour": "Orange"},
    19: {"name": "Vine Street", "type": "Property", "colour": "Orange"},
    20: {"name": "Free Parking", "type": "Corner", "colour": None},
    21: {"name": "Strand", "type": "Property", "colour": "Red"},
    22: {"name": "Chance", "type": "Chance", "colour": None},
    23: {"name": "Fleet Street", "type": "Property", "colour": "Red"},
    24: {"name": "Trafalgar Square", "type": "Property", "colour": "Red"},
    25: {"name": "Fenchurch Street Station", "type": "Station", "colour": None},
    26: {"name": "Leicester Square", "type": "Property", "colour": "Yellow"},
    27: {"name": "Coventry Street", "type": "Property", "colour": "Yellow"},
    28: {"name": "Water Works", "type": "Utility", "colour": None},
    29: {"name": "Piccadilly", "type": "Property", "colour": "Yellow"},
    30: {"name": "Go to Jail", "type": "Corner", "colour": None},
    31: {"name": "Regent Street", "type": "Property", "colour": "Green"},
    32: {"name": "Oxford Street", "type": "Property", "colour": "Green"},
    33: {"name": "Community Chest", "type": "Community Chest", "colour": None},
    34: {"name": "Bond Street", "type": "Property", "colour": "Green"},
    35: {"name": "Liverpool Street Station", "type": "Station", "colour": None},
    36: {"name": "Chance", "type": "Chance", "colour": None},
    37: {"name": "Park Lane", "type": "Property", "colour": "Dark Blue"},
    38: {"name": "Super Tax", "type": "Tax", "colour": None},
    39: {"name": "Mayfair", "type": "Property", "colour": "Dark Blue"}
}



def roll_dice():
    dice1 = np.random.randint(1, 7)
    dice2 = np.random.randint(1, 7)
    print(f"Dice rolled: {dice1} and {dice2}")
    return dice1 + dice2

class player:
    def __init__(self, name):
        self.name = name
        self.position = 0
        self.position_name = position_mapping[self.position]
        self.money = 1500
        self.full_board_cycles = 0

    def move(self, steps):
        step = 1
        while step <= steps:
            old_position = self.position
            self.position = (self.position + 1) % 40  
            new_position = (self.position)
            self.check_passed_go(old_position, new_position)

    def check_passed_go(self, old_pos, new_pos):
        if new_pos == 1 and old_pos == 0:
            self.full_board_cycles += 1
            self.money += 200

if __name__ == "__main__":
    player1 = player("Alice")
    player2 = player("Bob")
    for turn in range(10):
        for p in [player1, player2]:
            steps = roll_dice()
            p.move(steps) 
            position_name = position_mapping[p.position]["name"]       

            print(f"{p.name} rolled {steps} and moved to position {position_name} on turn {turn+1} with ${p.money}")