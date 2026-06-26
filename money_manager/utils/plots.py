def labels_and_values(rows, label_key, value_key):
    return {
        "labels": [row[label_key] for row in rows],
        "values": [round(row[value_key] or 0, 2) for row in rows],
    }
