from behave import when, then
import anyio

@when('I GET "{path}"')
def step_when_get(context, path: str):
    async def _do_get():
        context.response = await context.client.get(path)
    anyio.run(_do_get)

@then('the response status code should be {code:d}')
def step_then_status(context, code: int):
    assert context.response.status_code == code, (
        f"Expected {code}, got {context.response.status_code}. Body: {context.response.text}"
    )

@then('the JSON response should contain key "{key}"')
def step_then_json_contains_key(context, key: str):
    data = context.response.json()
    assert key in data, f"Expected key '{key}' in response JSON: {data}"
