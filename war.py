"""
war card game client and server
"""
import asyncio
from collections import namedtuple
from enum import Enum
import logging
import random
import socket
import socketserver
import threading
import sys


"""
Namedtuples work like classes, but are much more lightweight so they end
up being faster. It would be a good idea to keep objects in each of these
for each game which contain the game's state, for instance things like the
socket, the cards given, the cards still available, etc.
"""

# Stores the clients waiting to get connected to other clients
waiting_clients = []

class Command(Enum):
    """
    The byte values sent as the first byte of any message in the war protocol.
    """
    WANTGAME = 0
    GAMESTART = 1
    PLAYCARD = 2
    PLAYRESULT = 3


class Result(Enum):
    """
    The byte values sent as the payload byte of a PLAYRESULT message.
    """
    WIN = 0
    DRAW = 1
    LOSE = 2

def readexactly(sock, numbytes):
    """
    Accumulate exactly `numbytes` from `sock` and return those. If EOF is found
    before numbytes have been received, be sure to account for that here or in
    the caller.
    """
    result = b''
    while numbytes > 0:
        recent_bytes = sock.recv(numbytes)
        result += recent_bytes
        if len(recent_bytes) == 0:
            return -1
        numbytes -= len(recent_bytes)
        
    return result


def kill_game(game):
    """
    TODO: If either client sends a bad message, immediately nuke the game.
    """

    game.p1_socket.shutdown(socket.SHUT_RDWR)
    game.p1_socket.close()
    game.p2_socket.shutdown(socket.SHUT_RDWR)
    game.p2_socket.close()


def compare_cards(card1, card2):
    """
    TODO: Given an integer card representation, return -1 for card1 < card2,
    0 for card1 = card2, and 1 for card1 > card2
    """
    if (card1 - (13 * (card1 // 13))) > (card2 - (13 * (card2 // 13))):
        return 1
    elif (card1 - (13 * (card1 // 13))) < (card2 - (13 * (card2 // 13))):
        return -1
    else:
        return 0
    

def deal_cards():
    """
    TODO: Randomize a deck of cards (list of ints 0..51), and return two
    26 card "hands."
    """
    deck1 = list(range(0,52))
    deck2 = []
    for i in range(0, 26):
        picked_card = random.choice(deck1)
        deck2.append(picked_card)
        deck1.remove(picked_card)
        
    return (deck1, deck2)

def run_game(p1_socket, p2_socket):
    Game = namedtuple("Game", ["p1_socket", "p2_socket", "p1_hand", "p2_hand", "p1_wins", "p2_wins"])
    Game.p1_wins = 0
    Game.p2_wins = 0
    Game.p1_socket = p1_socket
    Game.p2_socket = p2_socket
    # Check for want game
    want1 = readexactly(Game.p1_socket, 2)
    want2 = readexactly(Game.p2_socket, 2)

    if want1 == -1 or want2 == -1 or want1[0] != Command.WANTGAME.value or want2[0] != Command.WANTGAME.value:
        logging.warning("Invalid game want.")
        kill_game(Game)
        return

    # Start game
    Game.p1_hand, Game.p2_hand = deal_cards()
    Game.p1_socket.sendall(bytes(Command.GAMESTART.value) + bytes(Game.p1_hand))
    Game.p2_socket.sendall(bytes(Command.GAMESTART.value) + bytes(Game.p2_hand))

    # Run rounds

    for i in range(0, 26):
        p1_card = readexactly(Game.p1_socket, 2)
        p2_card = readexactly(Game.p2_socket, 2)

        if p1_card == -1 or p2_card == -1 or p1_card[0] != Command.PLAYCARD.value or p2_card[0] != Command.PLAYCARD.value:
            logging.warning("Invalid move.")
            kill_game(Game)
            return

        comp = compare_cards(p1_card[1], p2_card[1])
        
        if comp == -1:
            p1_res, p2_res = Result.LOSE.value, Result.WIN.value
            Game.p1_socket.sendall(bytes([Command.PLAYRESULT.value, p1_res]))
            Game.p2_socket.sendall(bytes([Command.PLAYRESULT.value, p2_res]))
            Game.p2_wins += 1
        elif comp == 1:
            p1_res, p2_res = Result.WIN.value, Result.LOSE.value
            Game.p1_socket.sendall(bytes([Command.PLAYRESULT.value, p1_res]))
            Game.p2_socket.sendall(bytes([Command.PLAYRESULT.value, p2_res]))
            Game.p1_wins += 1
        else:
            Game.p1_socket.sendall(bytes([Command.PLAYRESULT.value, Result.DRAW.value]))
            Game.p2_socket.sendall(bytes([Command.PLAYRESULT.value, Result.DRAW.value]))

    if Game.p1_wins > Game.p2_wins:
        logging.info("Player 1 has won")
    elif Game.p1_wins < Game.p2_wins:
        logging.info("Player 2 has won")
    else:
        logging.info("The game was a draw")

    kill_game(Game)
    
def serve_game(host, port):
    """
    TODO: Open a socket for listening for new connections on host:port, and
    perform the war protocol to serve a game of war between each client.
    This function should run forever, continually serving clients.
    """

    ssocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ssocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ssocket.bind((host, port))
    ssocket.listen(2)
    logging.info(f"Server listening on: {host}, {port}")

    connected_clients = []

    # Wait for clients to connect
    while True:
        client_socket, addr = ssocket.accept()
        logging.debug(f"Client address: {addr}")
        connected_clients.append(client_socket)
        
        if (len(connected_clients) >= 2):
            p1_socket = connected_clients.pop(0)
            p2_socket = connected_clients.pop(0)

            threading.Thread(target=run_game, args=(p1_socket, p2_socket), daemon=True).start()

    

async def limit_client(host, port, loop, sem):
    """
    Limit the number of clients currently executing.
    You do not need to change this function.
    """
    async with sem:
        return await client(host, port, loop)

async def client(host, port, loop):
    """
    Run an individual client on a given event loop.
    You do not need to change this function.
    """
    try:
        reader, writer = await asyncio.open_connection(host, port)
        # send want game
        writer.write(b"\0\0")
        card_msg = await reader.readexactly(27)
        myscore = 0
        for card in card_msg[1:]:
            writer.write(bytes([Command.PLAYCARD.value, card]))
            result = await reader.readexactly(2)
            if result[1] == Result.WIN.value:
                myscore += 1
            elif result[1] == Result.LOSE.value:
                myscore -= 1
        if myscore > 0:
            result = "won"
        elif myscore < 0:
            result = "lost"
        else:
            result = "drew"
        logging.debug("Game complete, I %s", result)
        writer.close()
        return 1
    except ConnectionResetError:
        logging.error("ConnectionResetError")
        return 0
    except asyncio.streams.IncompleteReadError:
        logging.error("asyncio.streams.IncompleteReadError")
        return 0
    except OSError:
        logging.error("OSError")
        return 0

def main(args):
    """
    launch a client/server
    """
    host = args[1]
    port = int(args[2])
    if args[0] == "server":
        try:
            # your server should serve clients until the user presses ctrl+c
            serve_game(host, port)
        except KeyboardInterrupt:
            pass
        return
    else:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        
        asyncio.set_event_loop(loop)
        
    if args[0] == "client":
        loop.run_until_complete(client(host, port, loop))
    elif args[0] == "clients":
        sem = asyncio.Semaphore(1000)
        num_clients = int(args[3])
        clients = [limit_client(host, port, loop, sem)
                   for x in range(num_clients)]
        async def run_all_clients():
            """
            use `as_completed` to spawn all clients simultaneously
            and collect their results in arbitrary order.
            """
            completed_clients = 0
            for client_result in asyncio.as_completed(clients):
                completed_clients += await client_result
            return completed_clients
        res = loop.run_until_complete(
            asyncio.Task(run_all_clients(), loop=loop))
        logging.info("%d completed clients", res)

    loop.close()

if __name__ == "__main__":
    # Changing logging to DEBUG
    logging.basicConfig(level=logging.DEBUG)
    main(sys.argv[1:])
