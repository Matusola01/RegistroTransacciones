import requests

def get_dollar_price():
    url = "https://api.bluelytics.com.ar/v2/latest"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        # Extraer precios del dólar blue
        blue_prices = data.get("blue", {})
        buy_price = blue_prices.get("value_buy")
        sell_price = blue_prices.get("value_sell")

        if buy_price and sell_price:
            return {
                "buy": float(buy_price),
                "sell": float(sell_price)
            }
        else:
            print("Error: No se pudieron obtener los precios del dólar blue.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error al conectarse a la API: {e}")
        return None
