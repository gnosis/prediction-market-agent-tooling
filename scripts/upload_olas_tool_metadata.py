import json
import typing as t

from pydantic import BaseModel


class SchemaProperty(BaseModel):
    type: str
    description: str
    example: t.Optional[str] = None


class Schema(BaseModel):
    type: str
    properties: dict[str, SchemaProperty] = {}
    required: list[str] = []


class TypeDescriptionSchema(BaseModel):
    type: str
    description: str
    schema: t.Optional[Schema] = None


class Input(TypeDescriptionSchema):
    pass


class Output(TypeDescriptionSchema):
    pass


class Metadata(BaseModel):
    name: str
    description: str
    input: Input
    output: Output


def main(tool_name: str, description: str):
    # ToDo - Add input like this
    """
     api_key: str | None = kwargs.get("api_keys", {}).get("openai", None)
    if api_key is None:
        return error_response("No api key has been given.")

    gnosis_rpc_url: str | None = kwargs.get("api_keys", {}).get("gnosis_rpc_url", None)

    """
    print("oi")
    input = Input(
        type="text",
        description="The text to make a prediction on",
        schema=Schema(
            type="object",
            properties={
                "prompt": SchemaProperty(
                    type="string", description="The text to make a prediction on"
                ),
                "api_keys": SchemaProperty(
                    type="object", description="RPC_URL", schema=Schema()
                ),
            },
            required=["text"],
        ),
    )
    # ToDo - Output should be a schema
    output_properties = {
        "txParams": SchemaProperty(
            type="object", description="Unique identifier for the request"
        ),
        "result": SchemaProperty(
            type="string",
            description="Result information in JSON format as a string",
            example='{\n  "p_yes": 0.6,\n  "p_no": 0.4,\n  "confidence": 0.8,\n  "info_utility": 0.6\n}',
        ),
        "prompt": SchemaProperty(
            type="string", description="Prompt used for probability estimation."
        ),
    }
    output = Output(
        type="object",
        description="A JSON object containing the prediction and confidence",
        schema=Schema(
            type="object",
            properties=output_properties,
            required=output_properties.keys(),
        ),
    )
    metadata = Metadata(
        name=tool_name, description=description, input=input, output=output
    )

    filename = "metadata.json"
    with open(filename, "w") as json_file:
        # Write the dictionary to the file as JSON
        json.dump(metadata.model_dump_json(), json_file, indent=4)
    print(metadata.model_dump_json(indent=4, exclude_none=True))
    print(f"JSON string has been written to {filename}")


if __name__ == "__main__":
    tool_name = "a"
    description = "b"
    main(tool_name, description)
