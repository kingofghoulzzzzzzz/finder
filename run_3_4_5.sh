#!/bin/bash

# Step 1: Keep rerunning the first script if it exits with SIGTERM (code 143)
while true; do
    echo "Running 3.py..."
    python 3.py
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo "3.py completed successfully. Moving to next step."
        break
    elif [ $EXIT_CODE -eq 143 ]; then
        echo "3.py terminated by SIGTERM. Restarting..."
        sleep 2
    else
        echo "3.py exited with error code $EXIT_CODE. Aborting."
        exit $EXIT_CODE
    fi
done

# Step 2: Run 4.py
echo "Running 4.py..."
python3 4.py
SECOND_EXIT=$?
if [ $SECOND_EXIT -ne 0 ]; then
    echo "4.py failed with exit code $SECOND_EXIT. Aborting."
    exit $SECOND_EXIT
fi

# Step 3: Run 5.py
echo "Running 5.py..."
python3 5.py
THIRD_EXIT=$?
if [ $THIRD_EXIT -ne 0 ]; then
    echo "5.py failed with exit code $THIRD_EXIT. Aborting."
    exit $THIRD_EXIT
fi

echo "All scripts finished successfully."
exit 0
