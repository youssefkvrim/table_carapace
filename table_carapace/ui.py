"""UI utilities: screen control, progress bar, ASCII art."""

PROJECT_TITLE = r"""
 /$$$$$$$$        /$$       /$$                  /$$$$$$                        /$$                         /$$                 
|__  $$__/       | $$      | $$                 /$$__  $$                      | $$                        | $$                 
   | $$  /$$$$$$ | $$$$$$$ | $$  /$$$$$$       | $$  \__/  /$$$$$$  /$$$$$$$  /$$$$$$    /$$$$$$   /$$$$$$ | $$  /$$$$$$        
   | $$ |____  $$| $$__  $$| $$ /$$__  $$      | $$       /$$__  $$| $$__  $$|_  $$_/   /$$__  $$ /$$__  $$| $$ /$$__  $$       
   | $$  /$$$$$$$| $$  \ $$| $$| $$$$$$$$      | $$      | $$  \ $$| $$  \ $$  | $$    | $$  \__/| $$  \ $$| $$| $$$$$$$$       
   | $$ /$$__  $$| $$  | $$| $$| $$_____/      | $$    $$| $$  | $$| $$  | $$  | $$ /$$| $$      | $$  | $$| $$| $$_____/       
   | $$|  $$$$$$$| $$$$$$$/| $$|  $$$$$$$      |  $$$$$$/|  $$$$$$/| $$  | $$  |  $$$$/| $$      |  $$$$$$/| $$|  $$$$$$$       
   |__/ \_______/|_______/ |__/ \_______/       \______/  \______/ |__/  |__/   \___/  |__/       \______/ |__/ \_______/       

  /$$$$$$                                                                  
 /$$__  $$                                                                 
| $$  \__/  /$$$$$$   /$$$$$$  /$$$$$$   /$$$$$$   /$$$$$$   /$$$$$$$  /$$$$$$ 
| $$       |____  $$ /$$__  $$|____  $$ /$$__  $$ |____  $$ /$$_____/ /$$__  $$
| $$        /$$$$$$$| $$  \__/ /$$$$$$$| $$  \ $$  /$$$$$$$| $$      | $$$$$$$$
| $$    $$ /$$__  $$| $$      /$$__  $$| $$  | $$ /$$__  $$| $$      | $$_____/
|  $$$$$$/|  $$$$$$$| $$     |  $$$$$$$| $$$$$$$/|  $$$$$$$|  $$$$$$$|  $$$$$$$
 \______/  \_______/|__/      \_______/| $$____/  \_______/ \_______/ \_______/
                                       | $$                                    
                                       | $$                                    
                                       |__/                                    
"""

LICENSE_TEXT = """
================================================================================
                        PROPRIETARY SOFTWARE LICENSE
================================================================================

  This software is the exclusive property of SAFRAN SA and was developed for
  the Advanced Turbine Airfoils Platform division.

  PURPOSE: Ceramic shell photography system (Table de Prise de Photo des
  Carapaces Ceramiques) for crack detection following methylene blue testing.

  RESTRICTIONS:
    - Unauthorized copying, modification, or distribution is strictly prohibited
    - This software is licensed for use only on authorized SAFRAN equipment
    - Reverse engineering or decompilation is not permitted
    - All intellectual property rights remain with SAFRAN SA

  LEGAL NOTICE:
    Any unauthorized reproduction, distribution, modification, or use of this
    software constitutes a violation of intellectual property law and may
    result in civil and criminal penalties under applicable French and
    international regulations.

  SUPPORT & ISSUES:
    Contact: youssef.karim@safrangroup.com

  (C) 2025-2026 SAFRAN SA - All Rights Reserved
================================================================================
"""


def clear_screen():
    print('\033[2J\033[H', end='', flush=True)


def progress_bar(current, total, prefix="Progress", length=50):
    percent = current / total if total > 0 else 0
    filled = int(length * percent)
    bar = "\u2588" * filled + "\u2591" * (length - filled)
    print(f"\r{prefix} |{bar}| {current}/{total} ({percent*100:.1f}%)", end="", flush=True)
    if current == total:
        print()
