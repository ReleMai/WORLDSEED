"""Headless, deterministic presentation QA for the Dev44 conversation panel."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from pathlib import Path
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow


def main():
    output = Path('artifacts/dev44-dialogue-preview.png')
    term = PygameTerminal(1100, 760)
    term.enter()
    try:
        count = term.menu_page_size('npc_dialogue')
        choices = ['Ask about animals and wildlife', 'Ask about plants and crops',
                   'Ask about local resources', 'Ask which other towns they know',
                   'Ask for advice from their skills', 'Back to other topics']
        term._present_npc_dialogue('Tomas Morrow', [MenuRow(str(i), label) for i, label in enumerate(choices[:count])], 0,
                                  total=len(choices), data={
            'speaker': 'Tomas Morrow', 'role': 'Herder',
            'context': ['Night', 'Herder', 'Drink'],
            'relationship': {'trust': 4, 'affection': 3, 'familiarity': 21, 'community': 18},
            'response': 'I keep thinking about growing the herd. Hard to know whether that is hope or foolishness. '
                        'Our local livelihoods are farming and logging. We depend on trade for goods those workplaces do not supply. '
                        'Ask about the animals, crops, resources, towns I know, or skills I have practiced.',
        })
        term.pg.image.save(term.screen, str(output))
        print(output.resolve())
    finally:
        term.restore()


if __name__ == '__main__':
    main()
