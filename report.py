import os
import re
from config import *

def filter_files_by_mode_and_ticker(txt_files):
    if ANALYSIS_MODE == "all" and TICKER_FILTER == "all":
        return txt_files
    
    filtered_files = []
    for file_path in txt_files:
        filename = os.path.basename(file_path)
        filename_lower = filename.lower()
        
        # Извлекаем тикер (может быть через подчеркивание или пробел)
        ticker = "UNKNOWN"
        # Вариант 1: Ищем через подчеркивание (Strategy_IMOEXF_Min15_On.txt)
        parts_underscore = filename.split('_')
        if len(parts_underscore) > 1:
            ticker_candidate = parts_underscore[1]
            if not any(x in ticker_candidate.lower() for x in ['min', 'hour', 'on', 'long', 'short']):
                ticker = ticker_candidate
        
        # Вариант 2: Ищем через пробел (Strategy On IMOEXF 15.txt)
        parts_space = re.split(r'[\s_]+', filename)
        if len(parts_space) > 2 and 'on' in parts_space[1].lower():
            ticker = parts_space[2]
        
        # Фильтр по режиму
        mode_ok = False
        if ANALYSIS_MODE == "all":
            mode_ok = True
        elif ANALYSIS_MODE == "long":
            mode_ok = ("_long" in filename_lower or "onlylong" in filename_lower) and "onlyshort" not in filename_lower
        elif ANALYSIS_MODE == "short":
            mode_ok = ("_short" in filename_lower or "onlyshort" in filename_lower) and "onlylong" not in filename_lower
        elif ANALYSIS_MODE == "on":
            mode_ok = ("_on" in filename_lower or " on " in filename_lower) and "onlylong" not in filename_lower and "onlyshort" not in filename_lower
        
        # Фильтр по тикеру (регистронезависимый)
        ticker_ok = (TICKER_FILTER == "all" or TICKER_FILTER.lower() == ticker.lower())
        
        if mode_ok and ticker_ok:
            filtered_files.append(file_path)
    
    return filtered_files

def find_txt_files():
    txt_files = []
    for root, _, files in os.walk(DEFAULT_FOLDER):
        for file in files:
            if file.lower().endswith('.txt'):
                txt_files.append(os.path.join(root, file))
    
    return filter_files_by_mode_and_ticker(txt_files)

def parse_strategy_data(raw_text):
    params = []
    parts = raw_text.replace('@', '$').split('$')
    for part in parts:
        if '#' not in part:
            continue
        name_part, value_part = part.split('#', 1)
        param_name = name_part.strip()
        if not param_name or param_name.startswith('$'):
            continue
        param_value = value_part.split('#')[0].strip()
        params.append(f"{param_name} → {param_value}")

    metrics = {}
    start_idx = raw_text.find("BotTabSimple*")
    if start_idx != -1:
        start_idx += len("BotTabSimple*")
        end_idx = raw_text.find("*&", start_idx)
        if end_idx != -1:
            metrics_data = raw_text[start_idx:end_idx].split('*')
            if len(metrics_data) >= 11:
                try:
                    metrics = {
                        'Ticker': metrics_data[0],
                        'PosCount': int(metrics_data[1]),
                        'TotalProfit': float(metrics_data[2].replace(',', '.')),
                        'MaxDrowDown': abs(float(metrics_data[3].replace(',', '.'))),
                        'AverageProfit': float(metrics_data[4].replace(',', '.')),
                        'AverageProfit%': metrics_data[5],
                        'ProfitFactor': float(metrics_data[6].replace(',', '.')),
                        'PayOffRatio': metrics_data[7],
                        'Recovery': metrics_data[8],
                        'SharpRatio': float(metrics_data[10].replace(',', '.'))
                    }
                except (ValueError, IndexError):
                    return None, None, None, None, None
    
    first_part = raw_text.split('@')[0].strip().split()
    strategy_id = first_part[0] if first_part else "0"
    robot_name = first_part[0] if first_part else "UNKNOWN"
    
    # Улучшенное извлечение названия робота из имени файла
    file_name = raw_text.split('@^')[-1].split('@')[0].strip() if '@^' in raw_text else "UNKNOWN"
    # Удаляем расширение .txt если есть
    file_name = file_name.replace('.txt', '')
    # Извлекаем первое слово из имени файла (до первого пробела или подчеркивания)
    robot_name_from_file = re.split(r'[\s_]+', file_name)[0]
    
    return params, metrics, strategy_id, robot_name, robot_name_from_file

def load_and_filter_strategies(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        strategies = []
        records = content.split('@^')[1:]
        
        for record in records:
            params, metrics, strategy_id, robot_name, robot_name_from_file = parse_strategy_data(record)
            if not params or not metrics:
                continue
            
            # Проверка фильтра по названию робота (регистронезависимая)
            if ROBOT_NAME_FILTER != "all":
                # Проверяем в ID, имени робота и имени из файла
                robot_name_lower = robot_name.lower()
                robot_name_from_file_lower = robot_name_from_file.lower()
                filter_lower = ROBOT_NAME_FILTER.lower()
                
                if (filter_lower not in robot_name_lower and 
                    filter_lower not in robot_name_from_file_lower and
                    filter_lower not in os.path.basename(file_path).lower()):
                    continue
            
            if not (metrics['TotalProfit'] > MIN_PROFIT and
                   metrics['ProfitFactor'] > MIN_PROFIT_FACTOR and
                   metrics['SharpRatio'] > MIN_SHARPE_RATIO and
                   metrics['PosCount'] > MIN_TRADES and
                   metrics['MaxDrowDown'] > 0):
                continue
            
            strategies.append({
                'id': strategy_id,
                'name': robot_name_from_file if robot_name_from_file != "UNKNOWN" else robot_name,
                'params': params,
                'metrics': metrics,
                'file': os.path.basename(file_path),
                'file_path': file_path
            })
                
        return strategies
        
    except Exception:
        return []

def find_top_strategies():
    txt_files = find_txt_files()
    if not txt_files:
        return None
    
    all_robots = []
    for file_path in txt_files:
        robots = load_and_filter_strategies(file_path)
        if robots:
            best_robot = min(robots, key=lambda x: x['metrics']['MaxDrowDown'])
            all_robots.append(best_robot)
    
    if not all_robots:
        return None
    
    all_robots.sort(key=lambda x: x['metrics']['MaxDrowDown'])
    return all_robots[:TOP_COUNT]

def print_robot_details(strategy, index):
    metrics = strategy['metrics']
    print(f"\n=== Робот #{index + 1} ===")
    print(f"ID: {strategy['id']}")
    print(f"Название: {strategy['name']}")
    print(f"Тикер: {metrics['Ticker']}")
    print(f"Файл: {strategy['file']}")
    print(f"Полный путь: {strategy['file_path']}")
    
    print("\n✅ Основные метрики:")
    print(f"▪ Просадка: {metrics['MaxDrowDown']:.2f}")
    print(f"▪ Средняя прибыль %: {metrics['AverageProfit%']}")
    print(f"▪ Сделок: {metrics['PosCount']}")
    print(f"▪ Прибыль: {metrics['TotalProfit']:.2f}")
    print(f"▪ Профит-фактор: {metrics['ProfitFactor']:.2f}")
    print(f"▪ Коэф. Шарпа: {metrics['SharpRatio']:.2f}")
    print(f"▪ Средняя прибыль: {metrics['AverageProfit']:.2f}")
    print(f"▪ Отношение прибыли: {metrics['PayOffRatio']}")
    print(f"▪ Восстановление: {metrics['Recovery']}")

    print("\nПараметры стратегии:")
    for param in strategy['params']:
        print(f"• {param}")

def main():
    print("\n=== Анализатор торговых роботов ===")
    print(f"Папка для анализа: {DEFAULT_FOLDER}")
    print(f"Режим анализа: {ANALYSIS_MODE}")
    print(f"Фильтр по акции: {TICKER_FILTER}")
    print(f"Фильтр по названию робота: {ROBOT_NAME_FILTER}")
    print("\nКритерии отбора:")
    print(f"- Прибыль > {MIN_PROFIT} руб")
    print(f"- Профит-фактор > {MIN_PROFIT_FACTOR}")
    print(f"- Коэф. Шарпа > {MIN_SHARPE_RATIO}")
    print(f"- Сделок > {MIN_TRADES}")
    print(f"- Просадка > 0")
    print(f"- Топ {TOP_COUNT} по минимальной просадке")
    
    top_robots = find_top_strategies()
    
    if top_robots:
        print(f"\n✅ === ТОП-{TOP_COUNT} РОБОТОВ С МИНИМАЛЬНОЙ ПРОСАДКОЙ ===")
        for i, robot in enumerate(top_robots):
            print_robot_details(robot, i)
    else:
        print("\n❌ Не удалось найти подходящие стратегии")

if __name__ == '__main__':
    main()