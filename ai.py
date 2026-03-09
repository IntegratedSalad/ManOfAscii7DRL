from map import GameMap
from typing import Dict, Callable, Tuple, List, Optional

class FSM:
    '''
    states_map is a dictionary which holds functions associated with their ids (ints)
    allowed_transitions are tuples of size 2 (A, B) and define which state B can be transitioned to
    when being in a state A.
    '''
    def __init__(self, states_map: Dict[int, Callable], allowed_transitions: List[Tuple[int, int]]):
        self.states_map = states_map
        self.allowed_transitions = allowed_transitions
        self.current_state: int = None

    def return_state(self) -> Optional[Callable]:
        return self.states_map[self.current_state]

    def transition(self, state_id: int) -> Optional[Callable]:
        func = None
        if (self.is_transition_allowed(state_id)):
            self.current_state = state_id
            func = self.return_state()
        return func

    def is_transition_allowed(self, to_state: int) -> bool:
        for s_t in self.allowed_transitions:
            if s_t[1] == to_state and s_t[0] == self.current_state:
                return True
        return False

    def register_transition(self, transition: Tuple[int, int]) -> bool:
        '''
        Return True if there's no transition registered such as transition provided
        '''
        try:
            self.allowed_transitions.index(transition)
        except ValueError:
            return False
        self.allowed_transitions.append(transition)
        return True

    def register_state(self, state_id : int, func : Callable) -> bool:
        if any((x == state_id for x in self.states_map.keys())):
            return False
        self.states_map[state_id] = func
        return True

    def register_transisions(self, transisions: List[Tuple[int, int]]) -> bool:
        return all(self.register_transition(t) for t in transisions)

    def register_states(self, states: List[Tuple[int, Callable]]) -> bool:
        return all(self.register_state(state_id, func) for state_id, func in states)

class AI:
    '''
    AI defines abstract and concrete methods for taking actions to achieve certain goals
    Search for enemies/ search for crates
    Get ally health status
    Find ally with wounds
    etc.
    '''
    def __init__(self):
        self.brain = FSM()
        # TODO: Register generic states and transitions

class TeamAI(AI):
    pass

class IndividualAI(AI):
    pass

# AI needs to know about:
# 1. Map
# 2. Objects on map (blocked terrain)
# 3. Crates on map and items on ground
# 4. Friends and enemies

# Team AI has goals:
# 1. Ensure everyone has cover
# 2. Distribute most APs to the soldiers in danger
# 3. Target weakest enemy

# Individual AI has goals:
# 1. Destroy the opponents
# 2. Heal wounds
# 3. Get cover
# 4. Move towards enemy so that the aim increases
# 5. Collect supplies when low on ammo and bandages/iron supplements

# Each of these can be broken down to smaller goals.

# AI object will be a component of an actor
# If an Actor doesn't have AI, it's controlled by the player