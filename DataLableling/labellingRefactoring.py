import json
from pydantic import BaseModel, Field
from typing import List
import json_repair
from google import genai
from google.genai import types
import os
from isChopped import is_valid_code
from isValidJson import is_valid_obj


class RefactoredFile(BaseModel):
    filePath: str = Field(..., description="Path to the file either created or refactored.")
    fileContent: str = Field(..., description="The full content of the file")

class RefactoringOutput(BaseModel):
    refactored_files: List[RefactoredFile] = Field(..., description="List of all refactored files and their changes.")


def parse_json(text):
    try:
        return json_repair.loads(text)
    except:
        return None

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "my-service-account.json"

genai_client = genai.Client(
    vertexai=True,
    project="abiding-circle-461421-a8",
    location="global"
)

MODEL_NAME = "gemini-2.5-flash-preview-05-20"

def send_prompt(messages):
    contents = []
    for msg in messages:
        parts = [types.Part(text=msg["content"])]
        contents.append(types.Content(role=msg["role"], parts=parts))

    config = types.GenerateContentConfig(
        temperature=1,
        top_p=1,
        seed=0,
        max_output_tokens=10000,
        safety_settings=[],
        thinking_config=types.ThinkingConfig(
            thinking_budget=0,
        ),
    )

    try:
        response = genai_client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=config,
        )
        full_response = response.text

        parsed = parse_json(full_response)
        if parsed:
            return parsed
        else:
            print("Failed to parse Gemini response")
            return None

    except Exception as e:
        print("Gemini API Error:", str(e))
        return None


def refactor_solid_violations(input_path, output_path, unparsed_path):
    with open(input_path, "r") as f_in, open(output_path, "a") as f_out, open(unparsed_path, "a") as unparsed_f_out:
        for line in f_in:
            data = json.loads(line)

            solid_violations_refactoring_messages = [
                {
                    "role": "user",
                    "content": "\n".join([
                        "You are an expert Java developer specialized in applying Single Responsibility and Open-Closed principles through code refactoring.",
                        "You will be given one main Java file, with some dependencies (maybe none) along with a structured JSON detailing the detected Single Responsibility, Open-Closed violations in the main file.",
                        "Your task is to refactor the code to eliminate these violations while maintaining and improving overall code clarity and design.",
                        "",
                        "For reference, here are brief descriptions of the SRP and OCP principles:",
                        "- SRP (Single Responsibility): A class should have only one reason to change, i.e., one responsibility.",
                        "- OCP (Open/Closed): Classes should be open for extension, but closed for modification.",
                        "Apply a step-by-step reasoning process to identify the best approach for refactoring each violation.",
                        "After making initial changes, re-evaluate the result and improve it further if needed.",
                        "Then, reflect on the outcome: did you miss anything? Did your refactoring introduce new issues? If so, revise accordingly.",
                        "You should return the main file in case of being updated with its updated content.",
                        "You should return the created files with its content.",
                        "Never add multiple classes/enums/interfaces in the same file; if needed, create a new file for each.",
                        "After refactoring the main file and adding any new files, you must:",
                        "- Review all dependency files for references to the main file’s class, methods, or fields.",
                        "- Update those dependency files to reflect any renames, deletions, or new methods introduced in your refactor.",
                        "- Ensure there are no invalid references in dependency files (such as calling a method that no longer exists).",
                        "All updated dependency files should be included in your output alongside the main file and new files, following the Pydantic schema format.",
                        "Don't return a file unless it is updated or created.",
                        "",
                        "## Critical Output and Formatting Rules:",
                        "1. **Comment Formatting for Unfixable Dependencies:** This is a strict requirement. If a dependency cannot be updated due to missing context, you must leave a comment. IT IS CRITICAL that you add a line break (`\\n`) immediately after the comment. The code that follows the comment MUST start on a new line to avoid compilation errors.",
                        "2. **No Extra Content:** Do not include any explanation, introduction, or conclusion outside the final JSON output.",
                        "3. **Code Formatting:** Return the code in one line without extra spaces or break lines. Don't add any comments.",
                        "4. **JSON Structure:** You must follow the format defined in the Pydantic schema for the refactoring output.",
                        "",
                        "Be precise, complete, and objective. If no changes are needed, reflect that in the response.",
                        "## Code:",
                        json.dumps(data["prompt"], ensure_ascii=False),
                        "",
                        "## SO Violations:",
                        json.dumps(data["violations"], ensure_ascii=False),
                        "",
                        "## Pydantic Details:",
                        json.dumps(RefactoringOutput.model_json_schema(), ensure_ascii=False),
                        "",
                        "## Refactored Code:",
                        "```json"
                    ])
                }
            ]

            response = send_prompt(solid_violations_refactoring_messages)
            print(response)
            if not response:
                unparsed_f_out.write(line)
                continue
            refactored_files = response.get("refactored_files", [])
            result = {
                "project_id": data["project_id"],
                "chunk_id": data["chunk_id"],
                "prompt": {
                    "code": data["prompt"],
                    "violations": data["violations"]
                },
                "task": "SO Violations Refactoring",
                "output_schema": json.dumps(RefactoringOutput.model_json_schema(),
                                            ensure_ascii=False),
                "refactored_files": refactored_files
            }
            if is_valid_obj(result) and is_valid_code(result):
                print("ok")
                f_out.write(json.dumps(result) + "\n")
            else:
                print("not ok")
                unparsed_f_out.write(line)


def refactor_coupling(input_path, output_path, unparsed_path):
    with open(input_path, "r") as f_in, open(output_path, "a") as f_out, open(unparsed_path, "a") as unparsed_f_out:
        for line in f_in:
            data = json.loads(line)

            coupling_smells_refactoring_messages = [
                {
                    "role": "user",
                    "content": "\n".join([
                        "You are an expert Java developer focused on improving code maintainability by eliminating coupling code smells.",
                        "You will be given one or more Java files, along with a structured JSON identifying the detected coupling smells.",
                        "Your task is to refactor the code to reduce or eliminate excessive coupling while preserving intended behavior.",
                        "",
                        "For reference, here are the coupling smells you are expected to address:",
                        "- Feature Envy: A method accesses data from another class more than from its own.",
                        "- Inappropriate Intimacy: Classes that are too familiar and frequently access each other's internals.",
                        "- Incomplete Library Class: A library or third-party class lacks required features, leading users to implement workaround logic.",
                        "- Message Chains: A method navigates through multiple objects to retrieve a result (e.g., a.getB().getC().doSomething()).",
                        "- Middle Man: A class delegates most of its work to another class and adds little or no behavior of its own.",
                        "",
                        "Apply a step-by-step reasoning process to decide how best to restructure the design.",
                        "After making your initial refactor, recheck the output and refine it if necessary.",
                        "Reflect on your work: did you overlook any issue? Did your solution create a new one? If so, revise it.",
                        "",
                        "Do not include any explanation outside the JSON.",
                        "You must follow the format defined in the Pydantic schema for Coupling Refactoring output.",
                        "",
                        "Be precise, complete, and objective. If no changes are needed, reflect that in the response.",
                        "Do not generate any introduction or conclusion."
                        "## Code:",
                        json.dumps(data["prompt"], ensure_ascii=False),
                        "",
                        "## Coupling code smells:",
                        json.dumps(data["couplingSmells"], ensure_ascii=False),
                        "",
                        "## Pydantic Details:",
                        json.dumps(RefactoringOutput.model_json_schema(), ensure_ascii=False),
                        "",
                        "## Refactored Code:",
                        "```json"
                    ])
                }
            ]
            response = send_prompt(coupling_smells_refactoring_messages)
            if not response:
                unparsed_f_out.write(line)
                continue
            refactored_files = response.get("refactored_files", [])
            result = {
                "project_id": data["project_id"],
                "chunk_id": data["chunk_id"],
                "prompt": {
                    "code": data["prompt"],
                    "couplingSmells": data["couplingSmells"]
                },
                "task": "Coupling Smells Refactoring",
                "output_schema": json.dumps(RefactoringOutput.model_json_schema(),
                                            ensure_ascii=False),
                "refactored_files": refactored_files
            }
            f_out.write(json.dumps(result) + "\n")



refactor_solid_violations("Mariam.jsonl", "o.jsonl", "rerun.jsonl")
# refactor_solid_violations("", "", "rerun.jsonl")labellingRefactoringGemini.py