
// Best use for when you want to receive all data before processing it
function fetchFlashcards() {
    return new Promise((resolve, reject) => {
        let flashcards = [];
        let eventSource = new EventSource("http://localhost:8000/flashcards")

        eventSource.onmessage = (e) => {
            const data = JSON.parse(e.data)
            if (!data.done) {
                flashcards.push(data);
            } else {
                eventSource.close();
                resolve(flashcards);
            }
        }

        eventSource.onerror = (e) => {
            eventSource.close();
            reject(e);
        }
    })
}

// Use this for when you want a progress bar and you want to show items as it's being sent
let prograssBar = document.querySelector('.progress')
function fetchFlashcards2() {
    let flashcards = [];
    let received = 0;
    let max = 10;
    let source = new EventSource("http://localhost:8000/flashcards")

    source.onmessage = (e) => {
        const data = JSON.parse(e.data)
        if (data.done) {
            source.close()
            console.log(flashcards)
            console.log("Fetching Success!!")
        }

        data["id"] = Date.now()
        flashcards.push(data)
        received += 1;
        console.log(data)

        //Update progress bar
        let progress = (received / max) * 100;
        prograssBar.style.width = `${progress}%`
    }

    source.onerror = (err) => {
        source.close();
        alert("Generation failed")
    }
}

async function startFetching() {
    console.log("Started Fetching...")
    fetchFlashcards2()

    //Add an id to each card
    // flashcards.map(fl => fl["id"] = Date.now())
    // console.log(flashcards)
}

function generateIdSequential() {
    let latestIndex = Number(localStorage.getItem("latestIndex")) || 0;
    let newIndex = latestIndex + 1;
    localStorage.setItem("latestIndex", newIndex);

    return newIndex;
}