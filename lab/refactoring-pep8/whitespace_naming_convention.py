# by Kami Bigdely
# PEP8 - whitespaces and variable names.
# This is a guess game. Guess what number the computer has chosen!
import random
lowerLimit=0
UPPER_limit= 100
randomNumber = random.randint (lowerLimit ,UPPER_limit )
print ('The computer has selected a number between 0 and 100. Use your supernatural superpowers to guess what the number is.')
while True:
    UserGuess = int (input("Enter a number between 0 and 100 (including): "))
    if UserGuess> randomNumber:
        print ("Guess a smaller number.")
    elif UserGuess <randomNumber:
        print ("Guess a larger number.")
    else: #UserGuess == randomNumber:
        print ("You Won!")
        break
    