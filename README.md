# aiogNMI

## About

This Python library provides an efficient and lightweight gNMI client implementation that leverages asynchronous approach.

### Supported RPCs:

* Capabilities
* Get
* Set
* Subscribe (under development)

### Tested on:

* Arista EOS
* Nokia SR OS

Repository contains protobuf files from [gNMI](https://github.com/openconfig/gnmi/tree/master/proto) repo and based on gNMI release v0.10.0.
 Early gNMI version should work too, I've tested with 0.7.0 and it works well.

> **_NOTE:_**  At this moment supporting of the secure connections (with encryption or certificate) is in alpha version. You can use them, but I don't guarantee stable work.

## Install

Install with pip:

```bash
pip install aiognmi
```

## Examples

`Capabilities` RPC

```python
import asyncio

from aiognmi import AsyncgNMIClient


async def main():
    async with AsyncgNMIClient(host="test-1", port=6030, username="admin", password="admin", insecure=True) as client:
        resp = await client.get_capabilities()

    print(resp.result)


if __name__ == "__main__":
    asyncio.run(main())
```

`Get` RPC

```python
import asyncio

from aiognmi import AsyncgNMIClient


async def main():
    async with AsyncgNMIClient(host="test-1", port=6030, username="admin", password="admin", insecure=True) as client:
        resp = await client.get(
            paths=[
                "/interfaces/interface[name=Management0]",
            ]
        )

    print(resp.result)


if __name__ == "__main__":
    asyncio.run(main())
```

`Set` RPC

```python
import asyncio

from aiognmi import AsyncgNMIClient


async def main():
    async with AsyncgNMIClient(host="test-1", port=6030, username="admin", password="admin", insecure=True) as client:
        resp = await client.set(
            update=[
                {"path": "/interfaces/interface[name=Management0]/config", "data": {"description": "gnmi update test"}}
            ]
        )

    print(resp.result)


if __name__ == "__main__":
    asyncio.run(main())
```

## Credits

My work is inspired by these people:

1. [Anton Karneliuk](https://github.com/akarneliuk) and his [pyGNMI](https://github.com/akarneliuk/pygnmi) library
2. [Carl Montanari](https://github.com/carlmontanari) and his [scrapli](https://github.com/carlmontanari/scrapli) library
