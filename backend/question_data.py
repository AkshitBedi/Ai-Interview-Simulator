"""
backend/question_data.py

Phase 10: Rich Question Bank Expanded Content Catalog.
Contains 125 carefully authored, interview-grade questions across:
- Python (33 questions)
- Databases (33 questions)
- System Design (33 questions)
- Behavioral (26 questions)

Every question includes comprehensive rich metadata conforming to controlled taxonomies:
- topic & subtopic
- question_type & skill_type
- quality_tier
- expected_concepts
- common_mistakes
- ideal_answer_points
- prerequisites
"""

from typing import Any

ALL_AUTHORED_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": 1,
        "category": "Python",
        "difficulty": "medium",
        "question": "What is GIL in Python?",
        "topic": "Memory Management & Internals",
        "subtopic": "Global Interpreter Lock",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "GIL",
            "CPython",
            "thread safety",
            "CPU-bound vs I/O-bound",
            "bytecode execution"
        ],
        "common_mistakes": [
            "Believing GIL exists across all Python implementations (e.g. Jython, IronPython)",
            "Thinking GIL prevents all race conditions in application-level data structures",
            "Assuming multi-threaded I/O operations cannot run concurrently"
        ],
        "ideal_answer_points": [
            "CPython mutex preventing multiple native threads from executing Python bytecode simultaneously",
            "Ensures thread-safe memory management and reference counting without granular locks",
            "Limits CPU-bound concurrency on multi-core processors",
            "I/O-bound operations release the GIL during underlying system calls",
            "Workarounds include multiprocessing, native C extensions, or alternative runtimes"
        ],
        "prerequisites": [
            "Python threading basics",
            "Process vs thread concurrency"
        ]
    },
    {
        "id": 5,
        "category": "Python",
        "difficulty": "medium",
        "question": "Explain how memory management and the Global Interpreter Lock (GIL) work in CPython.",
        "topic": "Memory Management & Internals",
        "subtopic": "Reference Counting & GC",
        "question_type": "conceptual",
        "skill_type": "reasoning",
        "quality_tier": "core",
        "expected_concepts": [
            "reference counting",
            "cyclic garbage collector",
            "generational GC",
            "GIL",
            "PyObject"
        ],
        "common_mistakes": [
            "Confusing reference counting with generational cyclic garbage collection",
            "Assuming the GIL eliminates the need for synchronization locks in application code",
            "Thinking Python immediately frees cyclic references without GC cycles"
        ],
        "ideal_answer_points": [
            "Primary mechanism is reference counting tracked on PyObject ob_refcnt",
            "Cyclic garbage collector uses three generations to detect and break reference cycles",
            "GIL is a mutex protecting internal CPython state and reference counters",
            "Small object allocator (PyMalloc) manages allocations under 512 bytes via pools and arenas"
        ],
        "prerequisites": [
            "Memory management fundamentals"
        ]
    },
    {
        "id": 6,
        "category": "Python",
        "difficulty": "easy",
        "question": "What are Python generators and the yield keyword, and when would you use them over a standard list?",
        "topic": "Core Language & Data Structures",
        "subtopic": "Generators & Iterators",
        "question_type": "comparison",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "generators",
            "yield",
            "lazy evaluation",
            "memory efficiency",
            "iterator protocol"
        ],
        "common_mistakes": [
            "Thinking generators materialize complete sequences in memory",
            "Assuming generators support indexing or slicing like lists",
            "Not realizing a generator can only be consumed once before exhaustion"
        ],
        "ideal_answer_points": [
            "yield produces items on-demand and preserves internal execution state between calls",
            "Maintains O(1) memory footprint regardless of stream size",
            "Standard lists allocate entire sequences in memory allowing random access and multiple passes",
            "Generators are ideal for streaming files, large pipelines, and unbounded sequences"
        ],
        "prerequisites": [
            "Python functions and iterables"
        ]
    },
    {
        "id": 7,
        "category": "Python",
        "difficulty": "medium",
        "question": "Explain how Python decorators work under the hood, and how you would write a decorator that accepts arguments.",
        "topic": "OOP & Metaprogramming",
        "subtopic": "Decorators & Closures",
        "question_type": "implementation",
        "skill_type": "application",
        "quality_tier": "core",
        "expected_concepts": [
            "first-class functions",
            "closures",
            "higher-order functions",
            "functools.wraps",
            "decorator arguments"
        ],
        "common_mistakes": [
            "Omitting functools.wraps which erases original function name and docstring",
            "Failing to add the outermost factory function layer when accepting decorator arguments",
            "Hardcoding function parameters rather than forwarding *args and **kwargs"
        ],
        "ideal_answer_points": [
            "Decorators wrap a callable returning a new callable using lexical closures",
            "Decorators with arguments require 3 nested functions: decorator maker, decorator, and inner wrapper",
            "functools.wraps preserves metadata and introspection",
            "Correctly forwarding *args and **kwargs to the wrapped callable"
        ],
        "prerequisites": [
            "Python closures and first-class functions"
        ]
    },
    {
        "id": 8,
        "category": "Python",
        "difficulty": "hard",
        "question": "How does Python's asyncio event loop handle cooperative multitasking for high-concurrency I/O?",
        "topic": "Concurrency & Async",
        "subtopic": "Event Loop & Coroutines",
        "question_type": "conceptual",
        "skill_type": "reasoning",
        "quality_tier": "advanced",
        "expected_concepts": [
            "event loop",
            "coroutine",
            "async/await",
            "task scheduling",
            "selectors/epoll",
            "cooperative multitasking"
        ],
        "common_mistakes": [
            "Assuming asyncio spawns separate OS threads for concurrent tasks",
            "Calling synchronous blocking calls (e.g. time.sleep or requests.get) inside coroutines",
            "Confusing preemptive operating system scheduling with voluntary cooperative yielding"
        ],
        "ideal_answer_points": [
            "Single-threaded loop multiplexing non-blocking sockets via OS selectors (epoll/kqueue)",
            "Coroutines yield control back to the loop at await points",
            "I/O completion registers callbacks that wake suspended tasks",
            "CPU-bound routines block the entire event loop unless offloaded to ProcessPoolExecutor"
        ],
        "prerequisites": [
            "OS I/O multiplexing",
            "Python coroutines"
        ]
    },
    {
        "category": "Python",
        "difficulty": "easy",
        "question": "How does a Python list differ from a tuple in terms of memory overhead and mutability, and why are tuples hashable while lists are not?",
        "topic": "Core Language & Data Structures",
        "subtopic": "Lists vs Tuples",
        "question_type": "comparison",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "mutability",
            "immutability",
            "hashability",
            "memory over-allocation",
            "tuple optimization"
        ],
        "common_mistakes": [
            "Thinking tuples are simply write-protected lists",
            "Assuming tuples containing mutable elements (like lists) are hashable",
            "Overlooking list over-allocation growth strategy"
        ],
        "ideal_answer_points": [
            "Lists are mutable dynamic arrays with over-allocation for O(1) amortized appends",
            "Tuples are immutable fixed-size sequences with lower memory overhead",
            "Hashability requires immutable contents so hash values remain invariant over dictionary lifecycles",
            "Tuples containing mutable elements raise TypeError on hash() calls"
        ],
        "prerequisites": [
            "Basic Python data structures"
        ]
    },
    {
        "category": "Python",
        "difficulty": "easy",
        "question": "A developer writes: def append_item(val, target=[]): target.append(val); return target. Why does calling this function multiple times retain state across invocations, and how do you fix it idiomatically?",
        "topic": "Core Language & Data Structures",
        "subtopic": "Default Parameter Trap",
        "question_type": "debugging",
        "skill_type": "debugging",
        "quality_tier": "core",
        "expected_concepts": [
            "mutable default argument",
            "function definition time",
            "persistent binding",
            "None sentinel pattern"
        ],
        "common_mistakes": [
            "Believing default arguments evaluate on each function call",
            "Re-assigning target inside signature rather than using None sentinel",
            "Assuming assigning target = target or [] works safely for empty inputs"
        ],
        "ideal_answer_points": [
            "Default arguments evaluate once at function definition time when code object is compiled",
            "The mutable list instance binds permanently to the function's __defaults__ attribute",
            "Idiomatic resolution uses None sentinel: def append_item(val, target=None): if target is None: target = []",
            "Creates a fresh list on each invocation when no argument is supplied"
        ],
        "prerequisites": [
            "Python function definitions"
        ]
    },
    {
        "category": "Python",
        "difficulty": "medium",
        "question": "Compare the time complexity and memory characteristics of Python dictionaries versus collections.deque and list when implementing a FIFO queue.",
        "topic": "Core Language & Data Structures",
        "subtopic": "Queue Data Structures",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "core",
        "expected_concepts": [
            "collections.deque",
            "list.pop(0)",
            "O(n) shift",
            "doubly-linked block",
            "amortized O(1)"
        ],
        "common_mistakes": [
            "Using list.pop(0) without recognizing its O(n) memory copy penalty",
            "Suggesting dictionaries for queues without understanding ordered dict overhead",
            "Assuming deque indexing is O(1) like a contiguous list array"
        ],
        "ideal_answer_points": [
            "list.pop(0) is O(n) because all subsequent elements must shift left in memory",
            "collections.deque is implemented as doubly-linked blocks offering O(1) pops and appends from both ends",
            "deque has slight memory fragmentation due to block pointers but avoids large reallocations",
            "Dictionaries preserve insertion order (Python 3.7+) but are optimized for key lookups rather than queue operations"
        ],
        "prerequisites": [
            "Big-O notation",
            "Python data structures"
        ]
    },
    {
        "category": "Python",
        "difficulty": "medium",
        "question": "How do you implement a custom context manager in Python using both a class with __enter__ and __exit__ and the contextlib.contextmanager generator? How do you handle exception suppression?",
        "topic": "Core Language & Data Structures",
        "subtopic": "Context Managers",
        "question_type": "implementation",
        "skill_type": "application",
        "quality_tier": "core",
        "expected_concepts": [
            "context manager protocol",
            "__enter__",
            "__exit__",
            "contextlib.contextmanager",
            "exception suppression"
        ],
        "common_mistakes": [
            "Forgetting to return True from __exit__ to suppress handled exceptions",
            "Failing to use try...finally inside a @contextlib.contextmanager generator",
            "Not accepting exception arguments (exc_type, exc_val, exc_tb) in __exit__"
        ],
        "ideal_answer_points": [
            "Class protocol requires __enter__ returning resource and __exit__ receiving exc_type, exc_val, exc_tb",
            "Returning True from __exit__ tells Python runtime to suppress the raised exception",
            "@contextmanager decorator converts a generator yielding resource with cleanup in finally block",
            "If exception occurs in caller block, generator receives it at yield point"
        ],
        "prerequisites": [
            "Python OOP",
            "Exception handling"
        ]
    },
    {
        "category": "Python",
        "difficulty": "hard",
        "question": "You need to process a 20GB CSV log file on a server with only 4GB of RAM. How would you design a Python pipeline using iterators, itertools, and chunking to aggregate data without exhausting memory?",
        "topic": "Core Language & Data Structures",
        "subtopic": "Memory-Efficient Pipelines",
        "question_type": "scenario",
        "skill_type": "reasoning",
        "quality_tier": "advanced",
        "expected_concepts": [
            "streaming I/O",
            "generator pipelines",
            "itertools.islice",
            "chunking",
            "bounded memory usage"
        ],
        "common_mistakes": [
            "Calling readlines() or reading entire DataFrame into memory",
            "Accumulating intermediate data structures inside loops without yielding",
            "Failing to handle trailing partial chunks or stream cleanup"
        ],
        "ideal_answer_points": [
            "Iterate over file line-by-line using open() which provides lazy buffered reading",
            "Build composable generator pipeline: parse line -> filter events -> extract metric",
            "Use itertools.islice or chunked generators to aggregate batches into local accumulators",
            "Keep peak resident memory O(chunk_size) rather than O(file_size)"
        ],
        "prerequisites": [
            "Python generators",
            "File I/O"
        ]
    },
    {
        "category": "Python",
        "difficulty": "easy",
        "question": "What is the fundamental difference between 'is' and '==' in Python, and why is using 'is' to compare strings or integers dangerous?",
        "topic": "Core Language & Data Structures",
        "subtopic": "Identity vs Equality",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "identity vs equality",
            "id() memory address",
            "integer interning",
            "string interning",
            "__eq__"
        ],
        "common_mistakes": [
            "Assuming 'is' checks value equality",
            "Relying on CPython small integer caching (-5 to 256) in production code",
            "Thinking string interning applies to all dynamically computed strings"
        ],
        "ideal_answer_points": [
            "'==' checks value equivalence via __eq__ method",
            "'is' checks object identity (whether both variables point to the exact same memory address)",
            "CPython interns small integers (-5 to 256) and compile-time string constants as an implementation detail",
            "Comparing dynamic numbers or strings with 'is' creates intermittent bugs when allocations diverge"
        ],
        "prerequisites": [
            "Python basics"
        ]
    },
    {
        "category": "Python",
        "difficulty": "easy",
        "question": "What is the difference between copy.copy and copy.deepcopy in Python when handling nested data structures containing lists and dicts?",
        "topic": "Memory Management & Internals",
        "subtopic": "Shallow vs Deep Copy",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "shallow copy",
            "deep copy",
            "nested object references",
            "copy module",
            "recursive copying"
        ],
        "common_mistakes": [
            "Thinking shallow copy creates independent copies of nested sub-objects",
            "Overlooking infinite recursion risk with cyclic references in deep copy",
            "Assuming slicing list[:] creates a deep copy"
        ],
        "ideal_answer_points": [
            "copy.copy creates a new container but inserts references to the original nested objects",
            "Mutating a nested mutable object in a shallow copy reflects in the original structure",
            "copy.deepcopy recursively creates copies of all child and nested objects",
            "deepcopy maintains a memo dictionary to prevent infinite recursion on cyclic object graphs"
        ],
        "prerequisites": [
            "Python references and mutability"
        ]
    },
    {
        "category": "Python",
        "difficulty": "medium",
        "question": "In a long-running Python worker process, you observe steady memory growth even after request objects are dereferenced. How would you diagnose and resolve cyclic references and memory leaks using objgraph or tracemalloc?",
        "topic": "Memory Management & Internals",
        "subtopic": "Memory Leak Diagnostics",
        "question_type": "debugging",
        "skill_type": "debugging",
        "quality_tier": "advanced",
        "expected_concepts": [
            "tracemalloc",
            "objgraph",
            "memory snapshot",
            "reference cycles",
            "gc.garbage"
        ],
        "common_mistakes": [
            "Relying solely on OS resident set size without profiling internal Python heaps",
            "Assuming del immediately releases cyclic objects without garbage collection",
            "Leaving circular closures in bound callbacks without weak references"
        ],
        "ideal_answer_points": [
            "Take baseline and comparison heap snapshots with tracemalloc to identify growing allocations",
            "Use objgraph.show_growth() to inspect object type count deltas across worker requests",
            "Render reference chains using objgraph.show_backrefs() to find what retains references",
            "Break reference cycles using weakref.ref or weakref.proxy for event listeners and caches"
        ],
        "prerequisites": [
            "Python memory model",
            "Garbage collection"
        ]
    },
    {
        "category": "Python",
        "difficulty": "hard",
        "question": "What are __slots__ in Python classes? How do they alter internal memory layout and attribute lookup compared to a standard __dict__, and what capabilities do you lose when using them?",
        "topic": "Memory Management & Internals",
        "subtopic": "Slots and Object Layout",
        "question_type": "tradeoff",
        "skill_type": "reasoning",
        "quality_tier": "advanced",
        "expected_concepts": [
            "__slots__",
            "__dict__ elimination",
            "memory optimization",
            "descriptor access",
            "subclass inheritance"
        ],
        "common_mistakes": [
            "Assuming subclasses automatically inherit __slots__ behavior without redeclaring",
            "Believing __slots__ makes class attributes immutable",
            "Forgetting that instances lose dynamic attribute assignment unless '__dict__' is explicitly included in __slots__"
        ],
        "ideal_answer_points": [
            "Replaces per-instance __dict__ dictionary with a fixed-size array of descriptors",
            "Significantly reduces memory consumption when instantiating millions of small objects",
            "Accelerates attribute access speed through direct struct member offsets",
            "Disallows adding undeclared dynamic attributes unless '__dict__' is explicitly included in __slots__"
        ],
        "prerequisites": [
            "Python OOP internals",
            "Descriptors"
        ]
    },
    {
        "category": "Python",
        "difficulty": "hard",
        "question": "How does CPython's small object allocator (PyMalloc) and arena system manage memory allocation under 512 bytes, and why does Python memory not always get released back to the operating system after objects are deleted?",
        "topic": "Memory Management & Internals",
        "subtopic": "PyMalloc and Memory Fragmentation",
        "question_type": "conceptual",
        "skill_type": "reasoning",
        "quality_tier": "specialized",
        "expected_concepts": [
            "PyMalloc",
            "arenas",
            "pools",
            "blocks",
            "memory fragmentation",
            "OS page release"
        ],
        "common_mistakes": [
            "Thinking Python calls OS malloc/free directly for every object instantiation",
            "Assuming gc.collect() immediately shrinks the process RSS memory footprint",
            "Confusing Python heap deallocation with C runtime free()"
        ],
        "ideal_answer_points": [
            "PyMalloc divides memory into 256KB arenas, subdivided into 4KB pools containing uniform size-class blocks (up to 512 bytes)",
            "When an object is deleted, its block is returned to its pool, not immediately to the operating system",
            "An entire 256KB arena must be completely vacant before CPython releases the underlying memory back to the OS via free()",
            "Heap fragmentation prevents process resident memory from shrinking even when high object turnover occurs"
        ],
        "prerequisites": [
            "CPython internals",
            "Operating system virtual memory"
        ]
    },
    {
        "category": "Python",
        "difficulty": "easy",
        "question": "When should a Python engineer use threading versus multiprocessing, and how does the workload type (CPU-bound vs I/O-bound) dictate this decision?",
        "topic": "Concurrency & Async",
        "subtopic": "Threading vs Multiprocessing",
        "question_type": "comparison",
        "skill_type": "recall",
        "quality_tier": "core",
        "expected_concepts": [
            "threading",
            "multiprocessing",
            "CPU-bound",
            "I/O-bound",
            "GIL limitations"
        ],
        "common_mistakes": [
            "Using threading for CPU-heavy data computation expecting speedup on multi-core machines",
            "Overlooking IPC serialization (pickle) overhead in multiprocessing",
            "Assuming threads do not share memory"
        ],
        "ideal_answer_points": [
            "Threading uses shared process memory and lightweight threads, ideal for I/O-bound tasks where GIL is released during system calls",
            "Multiprocessing creates distinct OS processes with dedicated Python interpreters and independent GILs, bypassing GIL for CPU-bound tasks",
            "Multiprocessing requires IPC (pipes, queues) and data serialization via pickle",
            "Threading is lighter on system resources but cannot execute Python bytecodes across multiple cores simultaneously"
        ],
        "prerequisites": [
            "Concurrency basics"
        ]
    },
    {
        "category": "Python",
        "difficulty": "medium",
        "question": "You have 500 HTTP endpoints that need to be scraped concurrently every minute. Explain how you would implement this using aiohttp and asyncio.gather with an asyncio.Semaphore to throttle concurrent outbound requests.",
        "topic": "Concurrency & Async",
        "subtopic": "Async Rate-Limited Scraping",
        "question_type": "scenario",
        "skill_type": "application",
        "quality_tier": "core",
        "expected_concepts": [
            "aiohttp.ClientSession",
            "asyncio.gather",
            "asyncio.Semaphore",
            "connection pooling",
            "exception handling"
        ],
        "common_mistakes": [
            "Creating a fresh aiohttp.ClientSession per request rather than reusing a shared session",
            "Firing 500 unthrottled requests simultaneously, leading to socket exhaustion or remote rate limiting",
            "Using return_exceptions=False in gather which cancels remaining tasks on first failure"
        ],
        "ideal_answer_points": [
            "Instantiate a shared aiohttp.ClientSession with configured TCPConnector connection limits",
            "Wrap individual request coroutines in an asyncio.Semaphore context to cap concurrent active sockets",
            "Dispatch concurrent tasks using asyncio.gather with return_exceptions=True",
            "Handle HTTP errors, timeouts, and backoff retries within the wrapped coroutine"
        ],
        "prerequisites": [
            "Python asyncio",
            "HTTP client concepts"
        ]
    },
    {
        "category": "Python",
        "difficulty": "medium",
        "question": "A developer writes an asyncio web service, but under load, the event loop latency spikes to several seconds. You discover a synchronous time.sleep(5) call inside an async route handler. Why did this freeze all concurrent requests, and how should it be rewritten?",
        "topic": "Concurrency & Async",
        "subtopic": "Event Loop Blocking Bug",
        "question_type": "debugging",
        "skill_type": "debugging",
        "quality_tier": "advanced",
        "expected_concepts": [
            "event loop blocking",
            "cooperative multitasking",
            "time.sleep vs asyncio.sleep",
            "run_in_executor"
        ],
        "common_mistakes": [
            "Thinking an async def function makes synchronous blocking calls asynchronous automatically",
            "Suggesting threading locks to fix event loop starvation",
            "Not understanding that time.sleep suspends the entire OS thread running the loop"
        ],
        "ideal_answer_points": [
            "asyncio operates on a single thread; synchronous blocking operations block the entire event loop thread",
            "No other coroutines, network callbacks, or heartbeats can progress during the sleep duration",
            "For non-blocking delays, replace time.sleep with await asyncio.sleep()",
            "For blocking synchronous legacy libraries, offload execution via loop.run_in_executor(None, sync_func)"
        ],
        "prerequisites": [
            "Python asyncio event loop mechanics"
        ]
    },
    {
        "category": "Python",
        "difficulty": "hard",
        "question": "Compare Python's asyncio model with multi-threading and multi-processing in terms of context switching overhead, race condition risks, and debugging complexity.",
        "topic": "Concurrency & Async",
        "subtopic": "Concurrency Paradigms Comparison",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "advanced",
        "expected_concepts": [
            "preemptive vs cooperative",
            "context switching",
            "race conditions",
            "shared memory",
            "debugging tooling"
        ],
        "common_mistakes": [
            "Claiming asyncio is completely immune to race conditions between yield points",
            "Ignoring serialization cost when transferring state across processes",
            "Assuming threading always consumes less memory than async coroutines"
        ],
        "ideal_answer_points": [
            "asyncio: user-space cooperative context switching with minimal overhead, but race conditions can occur across await boundaries",
            "Threading: kernel-level preemptive context switching with shared memory, prone to thread-interleaving race conditions and deadlocks",
            "Multiprocessing: highest memory and context-switching overhead, but isolates memory and utilizes multiple CPU cores cleanly",
            "Debugging: multiprocessing requires IPC tracing; asyncio requires asynchronous stack trace inspection"
        ],
        "prerequisites": [
            "Operating system scheduling",
            "Python concurrency"
        ]
    },
    {
        "category": "Python",
        "difficulty": "hard",
        "question": "How would you implement a distributed worker pool in Python using multiprocessing.Queue or concurrent.futures.ProcessPoolExecutor that safely handles graceful shutdown on SIGTERM without corrupting in-flight jobs?",
        "topic": "Concurrency & Async",
        "subtopic": "Graceful Process Shutdown",
        "question_type": "implementation",
        "skill_type": "design",
        "quality_tier": "specialized",
        "expected_concepts": [
            "signal handling",
            "SIGTERM",
            "ProcessPoolExecutor",
            "multiprocessing.Event",
            "poison pill pattern",
            "in-flight task draining"
        ],
        "common_mistakes": [
            "Calling sys.exit(0) or terminate() directly inside the signal handler which kills children mid-write",
            "Ignoring closed pipe exceptions when workers attempt to write to queues after shutdown",
            "Failing to join child processes leading to zombie processes"
        ],
        "ideal_answer_points": [
            "Register a signal handler for SIGINT/SIGTERM setting a multiprocessing.Event or threading.Event shutdown flag",
            "Stop consuming new tasks and send sentinel poison pills (e.g. None) to worker queues",
            "Allow active workers to complete current jobs before cleanly breaking loop",
            "Call pool.shutdown(wait=True) or join child processes with a bounded timeout before final exit"
        ],
        "prerequisites": [
            "POSIX signals",
            "Python multiprocessing"
        ]
    },
    {
        "category": "Python",
        "difficulty": "easy",
        "question": "Explain how Python's @property decorator works, and when you would use it to replace direct attribute access or public getter/setter methods.",
        "topic": "OOP & Metaprogramming",
        "subtopic": "Properties and Encapsulation",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "@property",
            "getter/setter",
            "encapsulation",
            "data validation",
            "backward compatibility"
        ],
        "common_mistakes": [
            "Writing Java-style get_foo() and set_foo() methods throughout Python codebases",
            "Not defining a setter decorator when write access is required",
            "Executing expensive I/O operations inside a property access"
        ],
        "ideal_answer_points": [
            "Converts a method into a read-only attribute accessed via dot notation without parentheses",
            "Allows defining setter and deleter methods via @property_name.setter and @property_name.deleter",
            "Enables backward-compatible addition of validation or computation without breaking existing client attribute access",
            "Properties should remain lightweight and avoid expensive network or disk operations"
        ],
        "prerequisites": [
            "Python classes"
        ]
    },
    {
        "category": "Python",
        "difficulty": "medium",
        "question": "What is the Method Resolution Order (MRO) in Python multiple inheritance, and how does the C3 linearization algorithm prevent the diamond problem?",
        "topic": "OOP & Metaprogramming",
        "subtopic": "MRO and C3 Linearization",
        "question_type": "conceptual",
        "skill_type": "reasoning",
        "quality_tier": "core",
        "expected_concepts": [
            "MRO",
            "C3 linearization",
            "diamond problem",
            "super()",
            "monotonicity",
            "local precedence"
        ],
        "common_mistakes": [
            "Assuming Python uses simple depth-first search like legacy Python 2",
            "Calling Parent.__init__(self) explicitly instead of super().__init__() in multiple inheritance",
            "Believing MRO order can violate local class inheritance declarations"
        ],
        "ideal_answer_points": [
            "MRO defines the deterministic class lookup sequence for method and attribute resolution",
            "C3 linearization satisfies three properties: local precedence order, monotonicity, and single appearance",
            "Resolves the diamond problem by ensuring common base classes are evaluated after derived classes",
            "super() dynamically delegates to the next class in the runtime instance's MRO, not the lexical parent"
        ],
        "prerequisites": [
            "Python OOP",
            "Inheritance hierarchies"
        ]
    },
    {
        "category": "Python",
        "difficulty": "medium",
        "question": "How does Python's descriptor protocol (__get__, __set__, __delete__) operate, and how do frameworks like Django ORM or Pydantic use descriptors for field validation?",
        "topic": "OOP & Metaprogramming",
        "subtopic": "Descriptor Protocol",
        "question_type": "implementation",
        "skill_type": "application",
        "quality_tier": "advanced",
        "expected_concepts": [
            "descriptors",
            "__get__",
            "__set__",
            "data vs non-data descriptor",
            "ORM field mapping"
        ],
        "common_mistakes": [
            "Storing instance state on the descriptor instance itself rather than the host instance dictionary",
            "Confusing data descriptors (implementing __set__) with non-data descriptors (implementing only __get__)",
            "Not handling instance=None when accessed on class level"
        ],
        "ideal_answer_points": [
            "Descriptors are class attributes implementing one or more of __get__, __set__, or __delete__",
            "Data descriptors take precedence over the instance's __dict__ during attribute lookup",
            "Frameworks use descriptors to intercept attribute reads/writes for type coercion, dirty tracking, and DB serialization",
            "__set_name__ (Python 3.6+) automatically captures the attribute name assigned to the descriptor"
        ],
        "prerequisites": [
            "Python attribute lookup mechanics"
        ]
    },
    {
        "category": "Python",
        "difficulty": "hard",
        "question": "What is a Python metaclass, how does __new__ vs __init__ differ in metaclass creation, and how can you use metaclasses or __init_subclass__ to automatically register subclasses into a plugin registry?",
        "topic": "OOP & Metaprogramming",
        "subtopic": "Metaclasses and Plugin Registration",
        "question_type": "design",
        "skill_type": "design",
        "quality_tier": "specialized",
        "expected_concepts": [
            "metaclass",
            "type",
            "__init_subclass__",
            "__new__ vs __init__",
            "plugin registry pattern"
        ],
        "common_mistakes": [
            "Using a heavy metaclass when __init_subclass__ provides a simpler, cleaner solution",
            "Confusing class creation (__new__) with instance initialization (__init__)",
            "Overusing metaclasses where decorators or class factories suffice"
        ],
        "ideal_answer_points": [
            "A metaclass is the class of a class, defining how classes themselves are constructed and validated",
            "__new__ allocates and returns the class object, while __init__ initializes the newly created class object",
            "__init_subclass__ (Python 3.6+) provides a hook called when a subclass is defined, avoiding metaclass conflicts",
            "Enables automatic registration of subclasses into a dictionary registry for extensible plugin architectures"
        ],
        "prerequisites": [
            "Python OOP",
            "Metaprogramming concepts"
        ]
    },
    {
        "category": "Python",
        "difficulty": "easy",
        "question": "What is duck typing in Python, and how do Abstract Base Classes (ABCs) from the abc module enhance interface enforcement and runtime type verification?",
        "topic": "OOP & Metaprogramming",
        "subtopic": "Duck Typing and ABCs",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "duck typing",
            "Abstract Base Classes",
            "abc module",
            "@abstractmethod",
            "virtual subclasses"
        ],
        "common_mistakes": [
            "Thinking Python requires static interface declarations for polymorphism",
            "Failing to decorate methods with @abstractmethod, allowing instantiation of incomplete classes",
            "Over-restricting functions with isinstance checks when structural duck typing suffices"
        ],
        "ideal_answer_points": [
            "Duck typing focuses on what methods an object supports ('if it walks like a duck, it is a duck')",
            "Abstract Base Classes (ABCs) define explicit structural contracts and prevent instantiating incomplete classes",
            "Subclasses must implement all methods decorated with @abstractmethod to be instantiated",
            "ABCs support virtual subclass registration via register() method, enabling isinstance checks without inheritance"
        ],
        "prerequisites": [
            "Python OOP basics"
        ]
    },
    {
        "category": "Python",
        "difficulty": "easy",
        "question": "What is the purpose of fixtures in pytest, and how do different fixture scopes (function, module, session) affect test execution speed and state isolation?",
        "topic": "Testing & Performance Profiling",
        "subtopic": "Pytest Fixtures and Scoping",
        "question_type": "conceptual",
        "skill_type": "recall",
        "quality_tier": "core",
        "expected_concepts": [
            "pytest fixtures",
            "fixture scope",
            "function vs session",
            "state isolation",
            "teardown with yield"
        ],
        "common_mistakes": [
            "Using session scope for fixtures that mutate global state, creating test order dependency bugs",
            "Writing boilerplate setUp/tearDown methods instead of modular pytest fixtures",
            "Not using yield inside fixtures for deterministic resource cleanup"
        ],
        "ideal_answer_points": [
            "Fixtures provide modular setup and teardown for test dependencies via dependency injection",
            "Scopes: function (default, fresh instance per test), class, module, and session (single instance across all tests)",
            "Wider scopes (session) improve performance for expensive operations like test databases or containers",
            "Yield fixtures execute setup before yield and cleanup teardown logic after yield"
        ],
        "prerequisites": [
            "Testing fundamentals",
            "Python functions"
        ]
    },
    {
        "category": "Python",
        "difficulty": "medium",
        "question": "How do you use unittest.mock.patch to mock an external network API call in Python unit tests, and why is patching the symbol where it is imported rather than where it is defined critical?",
        "topic": "Testing & Performance Profiling",
        "subtopic": "Mocking and Patch Target Traps",
        "question_type": "scenario",
        "skill_type": "application",
        "quality_tier": "core",
        "expected_concepts": [
            "unittest.mock.patch",
            "patch where imported",
            "namespace resolution",
            "MagicMock",
            "mock side_effect"
        ],
        "common_mistakes": [
            "Patching 'requests.get' when the module under test did 'from requests import get'",
            "Not resetting mock state between test runs when using manual patch.start()",
            "Failing to mock both successful response payloads and network error side_effects"
        ],
        "ideal_answer_points": [
            "Target string must match the namespace where the object is looked up during execution, not where it was declared",
            "If my_module.py executes 'from requests import get', patch must target 'my_module.get'",
            "Use patch as a context manager or decorator to ensure automatic unpatching on test completion",
            "Configure return_value for response data or side_effect for simulating exceptions"
        ],
        "prerequisites": [
            "Python namespaces",
            "Unit testing"
        ]
    },
    {
        "category": "Python",
        "difficulty": "medium",
        "question": "A critical Python microservice is experiencing high CPU usage. Walk through how you would profile the code using cProfile, generate a flame graph, and pinpoint the computational bottleneck.",
        "topic": "Testing & Performance Profiling",
        "subtopic": "CPU Profiling with cProfile",
        "question_type": "debugging",
        "skill_type": "debugging",
        "quality_tier": "advanced",
        "expected_concepts": [
            "cProfile",
            "pstats",
            "flame graph",
            "cumtime vs tottime",
            "sampling profilers"
        ],
        "common_mistakes": [
            "Confusing tottime (time spent in function itself) with cumtime (time including sub-calls)",
            "Profiling in local environments with unrepresentative mock workloads",
            "Ignoring profiler overhead for deterministic instrumentation profilers"
        ],
        "ideal_answer_points": [
            "Execute code with python -m cProfile -o profile.pstats my_script.py",
            "Inspect top consumers via pstats sorted by tottime (self time) and cumtime (cumulative time)",
            "Convert profile output to flame graphs using tools like snakeviz, tuna, or py-spy",
            "Analyze visual width of flame stacks to isolate excessive loop iterations or unoptimized call paths"
        ],
        "prerequisites": [
            "Python CLI",
            "Performance optimization"
        ]
    },
    {
        "category": "Python",
        "difficulty": "hard",
        "question": "Compare performance optimization strategies in Python: optimizing algorithms with NumPy vectorization versus compiling hot paths with Cython or PyPy. When is each approach appropriate?",
        "topic": "Testing & Performance Profiling",
        "subtopic": "High-Performance Python Strategies",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "advanced",
        "expected_concepts": [
            "NumPy vectorization",
            "Cython",
            "PyPy JIT",
            "C-API overhead",
            "SIMD operations"
        ],
        "common_mistakes": [
            "Assuming PyPy automatically speeds up all programs including C-extension heavy packages",
            "Writing explicit Python loops over NumPy arrays rather than vectorized expressions",
            "Underestimating maintenance and packaging friction of Cython C compilation"
        ],
        "ideal_answer_points": [
            "NumPy: pushes array loops into pre-compiled C/Fortran libraries with SIMD; best for numerical and matrix computations",
            "PyPy: JIT compiler for pure Python code that optimizes repetitive loops without code modifications; struggles with C-extensions",
            "Cython: compiles typed Python/C code into native C extensions; best for custom algorithmic loops with complex data structures",
            "Choice depends on data layout, external dependencies, and deployment packaging constraints"
        ],
        "prerequisites": [
            "Python performance profiling",
            "C-extensions"
        ]
    },
    {
        "category": "Python",
        "difficulty": "easy",
        "question": "What is the role of virtual environments (venv) in Python development, and how do modern tools like poetry or uv improve dependency resolution and lockfile reproducibility?",
        "topic": "Ecosystem & Tooling",
        "subtopic": "Virtual Environments and Lockfiles",
        "question_type": "conceptual",
        "skill_type": "recall",
        "quality_tier": "core",
        "expected_concepts": [
            "venv",
            "site-packages",
            "pip",
            "poetry",
            "uv",
            "lockfiles",
            "dependency resolution"
        ],
        "common_mistakes": [
            "Installing application packages directly into the global system Python environment",
            "Checking virtual environment binary directories into version control",
            "Relying on loose unpinned requirements.txt files in production deployments"
        ],
        "ideal_answer_points": [
            "Virtual environments isolate site-packages and binary interpreters per project, preventing conflicting dependencies",
            "Global installs risk breaking system-level OS tools and colliding library versions",
            "Modern tools (poetry, uv) resolve complete dependency graphs using SAT-solvers and write deterministic lockfiles",
            "uv leverages Rust for fast package resolution and global disk caching"
        ],
        "prerequisites": [
            "Python packaging basics"
        ]
    },
    {
        "category": "Python",
        "difficulty": "medium",
        "question": "How do Python type hints and static type checkers like mypy improve code maintainability, and how would you configure type annotations for generic functions using TypeVar and Union/Optional?",
        "topic": "Ecosystem & Tooling",
        "subtopic": "Type Hints and Generics",
        "question_type": "scenario",
        "skill_type": "application",
        "quality_tier": "core",
        "expected_concepts": [
            "type hints",
            "mypy",
            "TypeVar",
            "Generic",
            "Optional/Union",
            "static analysis"
        ],
        "common_mistakes": [
            "Expecting Python runtime to enforce type hints without static checkers or Pydantic",
            "Using List/Dict from typing module on modern Python 3.9+ instead of built-in list/dict",
            "Not binding TypeVar when creating related input/output types"
        ],
        "ideal_answer_points": [
            "Type hints provide compile-time verification without incurring runtime performance overhead",
            "mypy statically analyzes type safety, preventing AttributeError and NoneType bugs before deployment",
            "TypeVar enables generic programming where return types match input parameter types",
            "Optional[T] (or T | None) explicitly handles nullable references, catching unhandled None cases"
        ],
        "prerequisites": [
            "Python syntax",
            "Type systems"
        ]
    },
    {
        "category": "Python",
        "difficulty": "medium",
        "question": "How would you package and distribute a Python library with a pyproject.toml file to ensure backward compatibility across Python 3.10 through 3.12?",
        "topic": "Ecosystem & Tooling",
        "subtopic": "Packaging with pyproject.toml",
        "question_type": "scenario",
        "skill_type": "design",
        "quality_tier": "core",
        "expected_concepts": [
            "pyproject.toml",
            "PEP 517/518",
            "build backend",
            "wheel vs sdist",
            "version matrix testing"
        ],
        "common_mistakes": [
            "Using legacy setup.py and setup.cfg files for new greenfield Python packages",
            "Hardcoding dependencies without environment markers for version-specific features",
            "Omitting automated matrix testing across Python versions in CI pipelines"
        ],
        "ideal_answer_points": [
            "Use pyproject.toml with a standard build backend like hatchling, flit, or setuptools",
            "Specify requires-python = '>=3.10' and declare dependencies with version constraints",
            "Use environment markers for version-specific polyfills (e.g. typing-extensions)",
            "Build standard source distributions (sdist) and universal wheels for PyPI distribution"
        ],
        "prerequisites": [
            "Python packaging",
            "CI/CD basics"
        ]
    },
    {
        "category": "Python",
        "difficulty": "hard",
        "question": "A production Python application crashes intermittently with a segmentation fault when using a C-extension library. How would you debug the crash using gdb with Python debug extensions (python-gdb.py)?",
        "topic": "Ecosystem & Tooling",
        "subtopic": "Debugging C-Extensions with GDB",
        "question_type": "debugging",
        "skill_type": "debugging",
        "quality_tier": "specialized",
        "expected_concepts": [
            "gdb",
            "python-gdb.py",
            "core dumps",
            "segmentation fault",
            "py-bt",
            "valgrind"
        ],
        "common_mistakes": [
            "Attempting to debug C-level segmentation faults using Python's standard pdb debugger",
            "Not enabling core dumps on the host system (ulimit -c unlimited)",
            "Debugging release binaries stripped of debugging symbols (-g)"
        ],
        "ideal_answer_points": [
            "Enable core dump generation via ulimit -c unlimited and locate the generated core file",
            "Load the core dump into gdb with the Python binary: gdb python core",
            "Source python-gdb.py to enable Python-aware commands like py-bt (Python backtrace) and py-locals",
            "Inspect the mixed C and Python stack frames to identify whether null pointers, memory corruption, or GIL violations triggered the crash"
        ],
        "prerequisites": [
            "C programming basics",
            "Linux systems debugging"
        ]
    },
    {
        "id": 9,
        "category": "Databases",
        "difficulty": "medium",
        "question": "Explain the difference between clustered and non-clustered indexes in relational databases.",
        "topic": "Indexing & Query Optimization",
        "subtopic": "B-Tree Indexes",
        "question_type": "comparison",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "clustered index",
            "non-clustered index",
            "physical data order",
            "leaf nodes",
            "B-tree",
            "lookup penalty"
        ],
        "common_mistakes": [
            "Thinking a table can have multiple clustered indexes",
            "Believing non-clustered indexes store full table rows",
            "Ignoring secondary-to-primary index pointer lookup overhead"
        ],
        "ideal_answer_points": [
            "Clustered index dictates the physical on-disk sort order of data rows",
            "A table can only have one clustered index; leaf nodes store the actual row data",
            "Non-clustered indexes are auxiliary B-trees with leaf nodes holding index keys and row pointers (or PKs)",
            "Secondary index lookups require traversing secondary B-tree then dereferencing into the clustered index"
        ],
        "prerequisites": [
            "Relational table storage basics"
        ]
    },
    {
        "id": 10,
        "category": "Databases",
        "difficulty": "hard",
        "question": "What are ACID properties in database transactions, and how does isolation level affect concurrency anomalies?",
        "topic": "Transactions & ACID Internals",
        "subtopic": "Isolation Levels & Anomalies",
        "question_type": "tradeoff",
        "skill_type": "reasoning",
        "quality_tier": "advanced",
        "expected_concepts": [
            "ACID",
            "isolation levels",
            "dirty read",
            "non-repeatable read",
            "phantom read",
            "write skew",
            "serialization"
        ],
        "common_mistakes": [
            "Confusing non-repeatable read with phantom read",
            "Assuming Read Committed prevents phantom reads",
            "Believing ACID guarantees are identical across all database engines"
        ],
        "ideal_answer_points": [
            "Atomicity (all-or-nothing), Consistency (schema constraints), Isolation (concurrency control), Durability (WAL persistence)",
            "ANSI isolation levels: Read Uncommitted, Read Committed, Repeatable Read, Serializable",
            "Read Committed prevents dirty reads; Repeatable Read prevents non-repeatable reads; Serializable prevents phantom reads and write skew",
            "Higher isolation increases lock contention or serialization aborts under optimistic MVCC"
        ],
        "prerequisites": [
            "Database transaction concepts",
            "Concurrency fundamentals"
        ]
    },
    {
        "id": 11,
        "category": "Databases",
        "difficulty": "easy",
        "question": "Explain the difference between INNER JOIN, LEFT JOIN, and FULL OUTER JOIN with practical examples.",
        "topic": "Relational Modeling & Schema Design",
        "subtopic": "SQL Joins & Sets",
        "question_type": "comparison",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "INNER JOIN",
            "LEFT JOIN",
            "FULL OUTER JOIN",
            "NULL handling",
            "relational sets"
        ],
        "common_mistakes": [
            "Thinking LEFT JOIN excludes rows where the right table matches",
            "Forgetting that unmatched rows in outer joins produce NULL values",
            "Assuming FULL OUTER JOIN is natively supported in SQLite without UNION workarounds"
        ],
        "ideal_answer_points": [
            "INNER JOIN returns only rows with matching join keys in both left and right tables",
            "LEFT JOIN preserves all rows from the left table and populates NULLs for unmatched right table columns",
            "FULL OUTER JOIN returns all rows from both tables, filling missing sides with NULLs",
            "Illustrating with concrete customer and order records"
        ],
        "prerequisites": [
            "Basic SQL syntax"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "easy",
        "question": "Explain the concepts of primary keys, foreign keys, and unique constraints in relational schema design, including why surrogate keys are often preferred over natural keys.",
        "topic": "Relational Modeling & Schema Design",
        "subtopic": "Keys and Constraints",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "primary key",
            "foreign key",
            "unique constraint",
            "surrogate key",
            "natural key",
            "referential integrity"
        ],
        "common_mistakes": [
            "Thinking natural keys never change over time (e.g. email or SSN)",
            "Confusing unique constraints with primary keys (unique constraints can permit NULL values)",
            "Omitting foreign key indexes, causing table scan cascades on deletions"
        ],
        "ideal_answer_points": [
            "Primary key uniquely identifies each entity row and forbids NULL values",
            "Foreign key enforces referential integrity between parent and child tables",
            "Surrogate keys (auto-increment integers or UUIDs) decouple relational identity from volatile business attributes",
            "Unique constraints ensure column uniqueness while allowing secondary index optimizations"
        ],
        "prerequisites": [
            "Relational modeling fundamentals"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "medium",
        "question": "What is database normalization up to Third Normal Form (1NF, 2NF, 3NF)? Under what operational conditions would an engineering team intentionally denormalize tables in an OLTP or OLAP system?",
        "topic": "Relational Modeling & Schema Design",
        "subtopic": "Normalization and Denormalization",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "core",
        "expected_concepts": [
            "1NF atomic values",
            "2NF partial dependency",
            "3NF transitive dependency",
            "denormalization",
            "read vs write performance"
        ],
        "common_mistakes": [
            "Confusing 2NF partial key dependencies with 3NF transitive non-key dependencies",
            "Assuming denormalization is always acceptable without acknowledging update anomalies",
            "Thinking OLAP data warehouses must adhere to strict 3NF rather than star/snowflake schemas"
        ],
        "ideal_answer_points": [
            "1NF requires atomic scalar values without repeating groups",
            "2NF eliminates partial dependencies on composite primary keys",
            "3NF eliminates transitive dependencies between non-prime attributes",
            "Denormalization reduces join overhead on read-heavy dashboards or high-throughput queries at the expense of redundant storage and update anomalies"
        ],
        "prerequisites": [
            "Relational database theory"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "medium",
        "question": "Design a relational schema for an e-commerce order management system that tracks customers, orders, order items, and inventory. How do you prevent negative stock while handling concurrent checkouts?",
        "topic": "Relational Modeling & Schema Design",
        "subtopic": "E-Commerce Inventory Schema",
        "question_type": "scenario",
        "skill_type": "design",
        "quality_tier": "core",
        "expected_concepts": [
            "normalization",
            "CHECK constraints",
            "inventory reservation",
            "optimistic locking",
            "atomic updates"
        ],
        "common_mistakes": [
            "Performing stock checks in application memory rather than atomic database updates",
            "Allowing race conditions where two checkouts simultaneously decrement inventory below zero",
            "Coupling product pricing directly to order items without snapshotting price at purchase time"
        ],
        "ideal_answer_points": [
            "Model entities: customers, orders, order_items (with captured unit_price), products, and inventory",
            "Enforce stock >= 0 via database CHECK constraint as a defensive safeguard",
            "Use atomic conditional updates: UPDATE inventory SET quantity = quantity - ? WHERE product_id = ? AND quantity >= ?",
            "Implement reservation timeouts or transactional saga states for multi-item checkouts"
        ],
        "prerequisites": [
            "SQL transactions",
            "Schema design"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "hard",
        "question": "How would you model soft-deletes across relational tables with foreign key constraints, and what query performance and unique-constraint challenges arise from soft-delete flags?",
        "topic": "Relational Modeling & Schema Design",
        "subtopic": "Soft Deletes and Referential Integrity",
        "question_type": "scenario",
        "skill_type": "design",
        "quality_tier": "advanced",
        "expected_concepts": [
            "soft delete flag",
            "deleted_at timestamp",
            "partial unique indexes",
            "foreign key cascading",
            "query view encapsulation"
        ],
        "common_mistakes": [
            "Using boolean is_deleted which prevents unique constraints on email or usernames for active users",
            "Forgetting to propagate soft-deletes to dependent child rows",
            "Allowing queries to accidentally leak soft-deleted rows by forgetting WHERE deleted_at IS NULL"
        ],
        "ideal_answer_points": [
            "Soft deletes use deleted_at TIMESTAMP NULL to track deletion time and active status",
            "Unique constraints must be partial: CREATE UNIQUE INDEX ON users (email) WHERE deleted_at IS NULL",
            "Foreign key constraints still reference soft-deleted rows without violating referential integrity",
            "Encapsulate active rows in database views or ORM global scopes to avoid accidental data leakage"
        ],
        "prerequisites": [
            "SQL schema design",
            "Indexing"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "easy",
        "question": "What is the purpose of database views, and how do materialized views differ in terms of physical storage and refresh latency?",
        "topic": "Relational Modeling & Schema Design",
        "subtopic": "Standard vs Materialized Views",
        "question_type": "conceptual",
        "skill_type": "recall",
        "quality_tier": "core",
        "expected_concepts": [
            "views",
            "materialized views",
            "query encapsulation",
            "disk caching",
            "refresh strategies"
        ],
        "common_mistakes": [
            "Thinking standard views store a precomputed copy of table data on disk",
            "Assuming materialized views update automatically on every base table write without performance penalty",
            "Overlooking lock contention during REFRESH MATERIALIZED VIEW in production"
        ],
        "ideal_answer_points": [
            "Standard views are saved SQL queries executed dynamically on invocation, consuming zero additional disk space",
            "Materialized views physically store the precomputed query results on disk like regular tables",
            "Materialized views require explicit refreshes (REFRESH MATERIALIZED VIEW CONCURRENTLY)",
            "Ideal for heavy aggregation queries and reporting where slight staleness is acceptable"
        ],
        "prerequisites": [
            "SQL queries"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "easy",
        "question": "How does a composite (multi-column) B-tree index work, and why does the column order in the index definition dictate whether the index can satisfy a given WHERE clause prefix?",
        "topic": "Indexing & Query Optimization",
        "subtopic": "Composite B-Tree Indexes",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "composite index",
            "leftmost prefix rule",
            "lexicographical sort",
            "range queries",
            "index skip scan"
        ],
        "common_mistakes": [
            "Assuming an index on (A, B) can optimize a query filtering solely on WHERE B = 10",
            "Placing range query columns before equality columns in composite indexes",
            "Creating separate single-column indexes on A and B expecting the planner to merge them efficiently"
        ],
        "ideal_answer_points": [
            "Data is sorted first by column A, then by column B within matching A values",
            "Follows the leftmost prefix rule: queries must filter on leading column A to leverage the B-tree",
            "Filter on B alone cannot narrow the B-tree search path because B values are scattered across different A nodes",
            "Order equality filter columns before range filter columns in composite index declarations"
        ],
        "prerequisites": [
            "B-Tree indexing fundamentals"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "medium",
        "question": "A SQL query filtering by WHERE created_at >= NOW() - INTERVAL '7 days' AND status = 'pending' is performing a full table scan despite having an index on created_at. How do you interpret an EXPLAIN ANALYZE output to fix it?",
        "topic": "Indexing & Query Optimization",
        "subtopic": "Query Plan Diagnostics",
        "question_type": "debugging",
        "skill_type": "debugging",
        "quality_tier": "core",
        "expected_concepts": [
            "EXPLAIN ANALYZE",
            "Seq Scan vs Index Scan",
            "planner cost estimates",
            "selectivity",
            "composite index (status, created_at)"
        ],
        "common_mistakes": [
            "Assuming database query planner always chooses an index regardless of row selectivity",
            "Thinking wrapping created_at in a function (e.g. DATE(created_at)) uses standard B-tree indexes",
            "Not checking outdated table statistics (ANALYZE)"
        ],
        "ideal_answer_points": [
            "Planner chooses Seq Scan if estimated rows returned exceed the threshold where random disk I/O beats sequential scans",
            "Single index on created_at requires fetching table rows to filter status, incurring heap fetch penalties",
            "Check EXPLAIN ANALYZE for estimated vs actual rows; run ANALYZE if cardinality estimates diverge",
            "Create a composite index on (status, created_at) allowing the planner to jump directly to pending rows within the date window"
        ],
        "prerequisites": [
            "SQL EXPLAIN execution plans"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "medium",
        "question": "Compare B-Tree indexes with Hash indexes and GiST/GIN inverted indexes in PostgreSQL. What query patterns and data types justify using GIN indexes over B-Trees?",
        "topic": "Indexing & Query Optimization",
        "subtopic": "Specialized Index Types",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "core",
        "expected_concepts": [
            "B-Tree",
            "Hash index",
            "GIN (Generalized Inverted Index)",
            "JSONB indexing",
            "full-text search",
            "array containment"
        ],
        "common_mistakes": [
            "Using B-Trees for JSONB key-value containment queries (@>)",
            "Using GIN indexes on columns with high update frequency without considering write amplification",
            "Thinking Hash indexes support range queries (<, >)"
        ],
        "ideal_answer_points": [
            "B-Trees support equality, range (<, <=, >, >=), and prefix search on scalar types",
            "Hash indexes support only exact equality (=) lookups with O(1) average lookup",
            "GIN (Generalized Inverted Index) maps elements/tokens to list of row IDs containing that element",
            "GIN is optimal for JSONB documents, arrays, and full-text search where multiple keys map to single rows"
        ],
        "prerequisites": [
            "PostgreSQL indexing",
            "JSONB data types"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "hard",
        "question": "You have a table with 100 million rows where queries filter on WHERE status = 'unprocessed', which represents less than 0.1% of the rows. How can partial (filtered) indexes dramatically reduce index size and write latency compared to standard indexing?",
        "topic": "Indexing & Query Optimization",
        "subtopic": "Partial and Filtered Indexes",
        "question_type": "scenario",
        "skill_type": "reasoning",
        "quality_tier": "advanced",
        "expected_concepts": [
            "partial index",
            "predicate filtering",
            "index bloat reduction",
            "write amplification",
            "cardinality skew"
        ],
        "common_mistakes": [
            "Indexing the entire status column when 99.9% of rows are 'completed'",
            "Querying with a predicate that does not match the exact WHERE clause in the partial index definition",
            "Forgetting that partial indexes still need maintenance when row status transitions"
        ],
        "ideal_answer_points": [
            "CREATE INDEX idx_unprocessed ON orders(id) WHERE status = 'unprocessed'",
            "Indexes only the 0.1% matching rows, keeping the B-tree tiny and fitting entirely in RAM",
            "Avoids index update writes for the 99.9% of rows updated between non-target statuses",
            "Queries matching the exact predicate jump straight to the compact partial index"
        ],
        "prerequisites": [
            "Advanced indexing",
            "Query planner behavior"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "hard",
        "question": "What causes an index scan to degrade into an index scan with heavy recheck or heap fetches, and how can an index-only scan (covering index via INCLUDE columns) eliminate table page lookups?",
        "topic": "Indexing & Query Optimization",
        "subtopic": "Covering Indexes and Index-Only Scans",
        "question_type": "debugging",
        "skill_type": "debugging",
        "quality_tier": "advanced",
        "expected_concepts": [
            "Index-Only Scan",
            "heap fetches",
            "visibility map",
            "covering index",
            "INCLUDE clause"
        ],
        "common_mistakes": [
            "Adding non-filtered payload columns into the primary index key rather than using INCLUDE",
            "Believing index-only scan never accesses heap even if visibility map pages are dirty",
            "Ignoring B-tree page bloat caused by including large text columns"
        ],
        "ideal_answer_points": [
            "Standard index scans locate row pointers in the index then read table heap pages for un-indexed columns",
            "Index-Only Scans satisfy queries entirely from the B-tree without visiting table heap pages",
            "In PostgreSQL, the visibility map must mark heap pages all-visible; dirty pages still require heap fetches",
            "The INCLUDE clause stores payload columns at B-tree leaf nodes without including them in tree branching keys"
        ],
        "prerequisites": [
            "PostgreSQL heap storage",
            "Index structure"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "easy",
        "question": "What is a database deadlock, and what standard detection or timeout mechanisms do database engines employ to break deadlocks?",
        "topic": "Transactions & ACID Internals",
        "subtopic": "Deadlock Detection and Resolution",
        "question_type": "conceptual",
        "skill_type": "recall",
        "quality_tier": "core",
        "expected_concepts": [
            "deadlock",
            "wait-for graph",
            "cycle detection",
            "lock timeout",
            "victim transaction abort"
        ],
        "common_mistakes": [
            "Thinking deadlocks can resolve themselves without transaction intervention or abort",
            "Assuming deadlocks only happen across different tables, rather than concurrent updates on the same table rows",
            "Failing to implement retry logic in client applications when deadlock exceptions occur"
        ],
        "ideal_answer_points": [
            "Deadlock occurs when two or more transactions hold locks the other needs, forming a circular wait",
            "Engines build a directed wait-for graph and run cycle detection algorithms periodically",
            "On detecting a cycle, the engine aborts one 'victim' transaction (typically lowest cost or newest) with a serialization/deadlock error",
            "Lock timeouts (lock_timeout) act as a secondary fallback if wait-for graph checking is disabled"
        ],
        "prerequisites": [
            "Database locks",
            "Transactions"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "medium",
        "question": "Two concurrent transactions execute SELECT balance FROM accounts WHERE id = 1 and subsequently update the balance based on the read value. How does this cause a lost update anomaly, and how does optimistic locking with version numbers or SELECT ... FOR UPDATE prevent it?",
        "topic": "Transactions & ACID Internals",
        "subtopic": "Lost Update and Concurrency Controls",
        "question_type": "scenario",
        "skill_type": "reasoning",
        "quality_tier": "core",
        "expected_concepts": [
            "lost update anomaly",
            "race condition",
            "pessimistic locking (SELECT FOR UPDATE)",
            "optimistic locking (version column)",
            "read committed isolation"
        ],
        "common_mistakes": [
            "Assuming standard Read Committed isolation prevents lost updates between separate SELECT and UPDATE statements",
            "Believing atomic single-statement updates (balance = balance - x) suffer from lost update bugs",
            "Using optimistic locking in high-contention environments leading to excessive retry thrashing"
        ],
        "ideal_answer_points": [
            "Both transactions read identical starting balance; the second committed update overwrites the first without accounting for its modification",
            "Pessimistic locking: SELECT ... FOR UPDATE acquires an exclusive row lock, forcing concurrent transactions to block until commit",
            "Optimistic locking: include a version column; UPDATE ... WHERE id = ? AND version = ? fails if another transaction committed first",
            "For simple increments/decrements, use atomic in-place updates: UPDATE accounts SET balance = balance - 50 WHERE id = 1 AND balance >= 50"
        ],
        "prerequisites": [
            "Transaction isolation",
            "SQL locking"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "medium",
        "question": "How does Multi-Version Concurrency Control (MVCC) allow readers to read data without locking out writers in engines like PostgreSQL and MySQL InnoDB?",
        "topic": "Transactions & ACID Internals",
        "subtopic": "MVCC Mechanics",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "MVCC",
            "xmin/xmax",
            "undo logs",
            "snapshot reads",
            "non-blocking reads"
        ],
        "common_mistakes": [
            "Thinking MVCC duplicates entire database tables for every active transaction",
            "Believing PostgreSQL and MySQL InnoDB implement MVCC identically (PostgreSQL uses in-table row versions; InnoDB uses undo log rollbacks)",
            "Assuming MVCC prevents write-write lock contention"
        ],
        "ideal_answer_points": [
            "When a row is updated or deleted, engines retain old versions rather than overwriting in-place",
            "PostgreSQL appends new tuple versions with xmin (creating transaction) and xmax (deleting transaction) headers",
            "MySQL InnoDB stores current row in clustered index and writes prior versions to undo log segments",
            "Transactions read consistent snapshot corresponding to their snapshot timestamp without taking shared read locks"
        ],
        "prerequisites": [
            "Database storage engines",
            "ACID transactions"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "hard",
        "question": "Explain the concept of Write Skew anomaly under Snapshot Isolation, and why standard repeatable read fails to prevent write skew while serializable isolation detects it.",
        "topic": "Transactions & ACID Internals",
        "subtopic": "Write Skew and Snapshot Isolation",
        "question_type": "scenario",
        "skill_type": "reasoning",
        "quality_tier": "advanced",
        "expected_concepts": [
            "write skew",
            "snapshot isolation",
            "repeatable read limitation",
            "serializable snapshot isolation (SSI)",
            "predicate locks"
        ],
        "common_mistakes": [
            "Thinking write skew is identical to dirty reads or non-repeatable reads",
            "Assuming repeatable read is sufficient for constraints that span multiple rows",
            "Believing write skew can occur when both transactions modify the exact same row"
        ],
        "ideal_answer_points": [
            "Write skew occurs when two concurrent transactions read overlapping data sets, satisfy an invariant, but write disjoint rows that violate the invariant",
            "Example: doctors on call where constraint requires at least one doctor on duty; two doctors simultaneously check count > 1 and both take leave",
            "Repeatable read allows this because neither transaction modified a row the other locked or modified directly",
            "Serializable isolation (SSI) tracks read-write dependencies (SIREAD locks) and aborts one transaction with a serialization failure"
        ],
        "prerequisites": [
            "Transaction anomalies",
            "MVCC Snapshot Isolation"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "hard",
        "question": "How do relational databases handle distributed transactions across multiple independent databases using the Two-Phase Commit (2PC) protocol, and what failure mode causes nodes to block indefinitely?",
        "topic": "Transactions & ACID Internals",
        "subtopic": "Two-Phase Commit Protocol",
        "question_type": "debugging",
        "skill_type": "debugging",
        "quality_tier": "specialized",
        "expected_concepts": [
            "Two-Phase Commit (2PC)",
            "coordinator node",
            "prepare phase",
            "commit phase",
            "coordinator failure",
            "blocking protocol"
        ],
        "common_mistakes": [
            "Assuming 2PC is fully partition-tolerant without blocking risk",
            "Confusing 2PC with 2-Phase Locking (2PL)",
            "Overlooking resource lock holding during the uncertainty window between prepare and commit"
        ],
        "ideal_answer_points": [
            "Phase 1 (Prepare): coordinator asks participants to validate constraints, write WAL redo/undo logs, and vote YES or NO",
            "Phase 2 (Commit): if all vote YES, coordinator logs COMMIT and sends commit orders; if any vote NO, aborts all",
            "Failure mode: if the coordinator crashes permanently after participants vote YES but before sending COMMIT, participants remain blocked holding locks indefinitely",
            "3PC or Paxos/Raft consensus groups are used to mitigate coordinator single-point-of-failure blocking"
        ],
        "prerequisites": [
            "Distributed systems",
            "Database ACID protocols"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "easy",
        "question": "What is read replica lag in asynchronous database replication, and how does it cause read-after-write inconsistency for a user who immediately refreshes their profile page?",
        "topic": "Replication, Partitioning & Scaling",
        "subtopic": "Replica Lag and Read Consistency",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "replication lag",
            "asynchronous replication",
            "read-after-write consistency",
            "WAL streaming",
            "sticky routing"
        ],
        "common_mistakes": [
            "Assuming asynchronous replication delivers zero-latency replication across nodes",
            "Directing user-profile reads to stale read replicas immediately after an update write",
            "Thinking increasing replica node count reduces replication lag"
        ],
        "ideal_answer_points": [
            "Primary writes transactions and streams WAL logs asynchronously to read replicas over the network",
            "Network latency or high replica query load delays WAL replay, creating replication lag",
            "If user updates their profile on primary and immediately reads from replica, stale pre-update data is returned",
            "Mitigate using read-your-writes routing (route writes and subsequent immediate reads from same user to primary for N seconds)"
        ],
        "prerequisites": [
            "Database replication basics"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "medium",
        "question": "Compare synchronous replication with asynchronous replication in terms of write latency, data durability, and failover behavior during network partitions.",
        "topic": "Replication, Partitioning & Scaling",
        "subtopic": "Sync vs Async Replication",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "core",
        "expected_concepts": [
            "synchronous replication",
            "asynchronous replication",
            "commit acknowledgement",
            "failover durability",
            "network partition impact"
        ],
        "common_mistakes": [
            "Believing synchronous replication has zero latency penalty on client commits",
            "Assuming asynchronous failover never loses committed transactions",
            "Ignoring semi-synchronous replication middle-ground configurations"
        ],
        "ideal_answer_points": [
            "Synchronous: primary waits for at least one replica to acknowledge WAL receipt before confirming commit to client; guarantees zero data loss on primary failure",
            "Synchronous tradeoff: client write latency increases by network round-trip time; network partitions can freeze primary writes",
            "Asynchronous: primary acknowledges commit immediately; high write throughput and low latency, but un-replicated commits are lost if primary dies",
            "Semi-synchronous replication confirms commit when one replica logs WAL, balancing latency and durability"
        ],
        "prerequisites": [
            "High availability",
            "Database replication"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "medium",
        "question": "How does horizontal database sharding work, and what are the tradeoffs between range-based sharding versus consistent hash-based sharding when distributing data across database shards?",
        "topic": "Replication, Partitioning & Scaling",
        "subtopic": "Database Sharding Strategies",
        "question_type": "design",
        "skill_type": "design",
        "quality_tier": "advanced",
        "expected_concepts": [
            "horizontal sharding",
            "shard key",
            "range sharding",
            "hash sharding",
            "cross-shard joins",
            "rebalancing"
        ],
        "common_mistakes": [
            "Choosing a shard key that creates hotspot nodes (e.g. monotonically increasing timestamps in hash sharding)",
            "Assuming distributed cross-shard transactions perform as fast as single-node queries",
            "Overlooking rebalancing migration complexity when adding new physical shards"
        ],
        "ideal_answer_points": [
            "Sharding partitions table rows across independent physical database instances via a shard key",
            "Range-based sharding: efficient for range scans, but prone to write hotspots on leading ranges (e.g. current dates)",
            "Hash-based sharding: uniformly distributes write traffic across shards, but range queries require scatter-gather scans across all shards",
            "Cross-shard joins and distributed two-phase commits introduce high network latency and operational complexity"
        ],
        "prerequisites": [
            "Database scaling",
            "Distributed architecture"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "hard",
        "question": "An e-commerce platform needs to partition a 2TB payments table. Explain how you would implement declarative range partitioning by timestamp in PostgreSQL, and how partition pruning improves query response time.",
        "topic": "Replication, Partitioning & Scaling",
        "subtopic": "Table Partitioning and Pruning",
        "question_type": "scenario",
        "skill_type": "design",
        "quality_tier": "advanced",
        "expected_concepts": [
            "declarative partitioning",
            "range partitioning",
            "partition pruning",
            "constraint exclusion",
            "maintenance detachment"
        ],
        "common_mistakes": [
            "Using partition keys not included in primary or unique key definitions",
            "Creating hundreds of tiny partitions causing query planner overhead",
            "Forgetting to create individual partition indexes"
        ],
        "ideal_answer_points": [
            "Define parent table with PARTITION BY RANGE (payment_date)",
            "Create child partition tables for monthly or quarterly ranges",
            "Partition pruning allows the query planner to exclude irrelevant partitions entirely based on query WHERE clauses",
            "Maintenance benefits: archiving old data via ALTER TABLE DETACH PARTITION is an instantaneous metadata operation compared to slow, locked DELETE scans"
        ],
        "prerequisites": [
            "PostgreSQL table architecture",
            "Query planning"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "hard",
        "question": "During a primary database failover, split-brain occurs where two nodes believe they are the authoritative primary. What consensus mechanisms (such as Raft or quorum voting) prevent split-brain during automated failover?",
        "topic": "Replication, Partitioning & Scaling",
        "subtopic": "Split-Brain and Consensus Protocols",
        "question_type": "scenario",
        "skill_type": "reasoning",
        "quality_tier": "specialized",
        "expected_concepts": [
            "split-brain",
            "quorum voting",
            "fencing tokens",
            "STONITH",
            "Raft consensus",
            "dual primaries"
        ],
        "common_mistakes": [
            "Relying on simple heartbeat timeouts without quorum consensus to trigger primary promotions",
            "Allowing both isolated network partitions to accept client writes simultaneously",
            "Not employing fencing mechanisms to forcefully isolate or power down old primaries"
        ],
        "ideal_answer_points": [
            "Split-brain results in divergent data histories across nodes that cannot be automatically reconciled without data loss",
            "Quorum consensus requires promotion approval from a strict majority (N/2 + 1) of cluster nodes",
            "Fencing tokens (monotonically increasing generation numbers) ensure storage rejected writes from stale primaries",
            "Tools like Patroni or Raft coordinate leases via distributed key-value stores (etcd/Consul) with STONITH node fencing"
        ],
        "prerequisites": [
            "Distributed consensus",
            "High availability architecture"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "easy",
        "question": "What is the Write-Ahead Log (WAL) or redo log in relational database engines, and why is writing to the WAL sequentially faster than modifying data pages directly on disk?",
        "topic": "Storage Engines & Buffer Management",
        "subtopic": "Write-Ahead Logging",
        "question_type": "conceptual",
        "skill_type": "recall",
        "quality_tier": "core",
        "expected_concepts": [
            "Write-Ahead Log (WAL)",
            "redo log",
            "sequential I/O vs random I/O",
            "fsync",
            "crash recovery"
        ],
        "common_mistakes": [
            "Assuming database changes are written directly to table heap files before transaction commit returns",
            "Thinking WAL records contain full copies of entire database tables",
            "Confusing undo logs (used for rollbacks and MVCC) with redo logs (used for crash durability)"
        ],
        "ideal_answer_points": [
            "WAL rule: state changes must be appended to disk log before the corresponding data pages in buffer memory are flushed to disk",
            "Append-only sequential disk writes are orders of magnitude faster than random disk I/O on scattered table pages",
            "Ensures ACID durability while allowing database engine to flush dirty buffer pool pages asynchronously in batches",
            "During crash recovery, the engine replays WAL records to reconstruct committed states not yet persisted to data files"
        ],
        "prerequisites": [
            "Disk I/O mechanics",
            "ACID transactions"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "medium",
        "question": "How does the database buffer pool cache disk pages in memory, and how do dirty page flushing policies like checkpointing ensure durability without blocking concurrent transactions?",
        "topic": "Storage Engines & Buffer Management",
        "subtopic": "Buffer Pool and Checkpointing",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "buffer pool",
            "dirty pages",
            "checkpointing",
            "LRU/Clock eviction",
            "fuzzy checkpoints"
        ],
        "common_mistakes": [
            "Believing checkpoints freeze all incoming transactions and queries",
            "Thinking all read queries hit disk directly rather than checking buffer pool caches first",
            "Setting buffer pool sizes too low or failing to account for OS page cache interaction"
        ],
        "ideal_answer_points": [
            "Buffer pool caches table and index disk pages in RAM; reads check buffer pool first to avoid physical disk I/O",
            "Pages modified in memory are marked 'dirty' and scheduled for background disk flushing",
            "Checkpoints periodically flush dirty pages to disk and write a checkpoint marker into the WAL",
            "Crash recovery only needs to replay WAL entries generated after the latest completed checkpoint record"
        ],
        "prerequisites": [
            "Operating system paging",
            "Database storage architecture"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "medium",
        "question": "Compare the storage architecture of B-Trees (in-place updates) with Log-Structured Merge (LSM) Trees (append-only SSTables and compaction). Why are LSM trees preferred for high write-throughput workloads?",
        "topic": "Storage Engines & Buffer Management",
        "subtopic": "B-Trees vs LSM Trees",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "advanced",
        "expected_concepts": [
            "B-Tree",
            "LSM Tree",
            "MemTable",
            "SSTables",
            "compaction",
            "write amplification vs read amplification"
        ],
        "common_mistakes": [
            "Assuming LSM trees provide faster point lookups than B-Trees without Bloom filter optimizations",
            "Ignoring compaction I/O storms and space amplification in LSM trees",
            "Thinking B-Trees cannot handle writes"
        ],
        "ideal_answer_points": [
            "B-Trees write updates in-place to fixed-size disk pages, generating random I/O and high write amplification",
            "LSM Trees buffer writes in an in-memory MemTable and flush immutable sequential Sorted String Tables (SSTables) to disk",
            "LSM converts random writes into purely sequential disk I/O, achieving dramatic write throughput advantages",
            "LSM reads require checking multiple SSTable levels, mitigated via Bloom filters and background compaction"
        ],
        "prerequisites": [
            "Data structures",
            "Storage engine internals"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "hard",
        "question": "In PostgreSQL, what is table bloat, why do frequent UPDATE and DELETE queries cause dead tuples to accumulate, and how does autovacuum prevent transaction ID wraparound?",
        "topic": "Storage Engines & Buffer Management",
        "subtopic": "PostgreSQL Bloat and Vacuuming",
        "question_type": "debugging",
        "skill_type": "debugging",
        "quality_tier": "specialized",
        "expected_concepts": [
            "table bloat",
            "dead tuples",
            "autovacuum",
            "VACUUM FULL",
            "transaction ID (XID) wraparound",
            "free space map"
        ],
        "common_mistakes": [
            "Running VACUUM FULL during peak production hours without realizing it takes an exclusive table lock",
            "Disabling autovacuum to improve short-term write speeds, leading to catastrophic database shutdown",
            "Confusing dead tuple cleanup with OS file truncation"
        ],
        "ideal_answer_points": [
            "MVCC marks updated and deleted rows as dead tuples rather than immediately reclaiming disk space",
            "Accumulated dead tuples bloat tables and indexes, forcing sequential scans to read empty disk pages",
            "Standard VACUUM marks dead tuple space reusable in the Free Space Map without shrinking file size on disk",
            "Autovacuum aggressively freezes ancient transaction IDs before the 2-billion transaction limit to prevent wraparound data loss"
        ],
        "prerequisites": [
            "PostgreSQL MVCC",
            "Operating system file systems"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "hard",
        "question": "Predict what happens to database latency and system throughput when a database workload exhausts the buffer pool hit ratio from 99% down to 60%. What disk I/O bottlenecks emerge?",
        "topic": "Storage Engines & Buffer Management",
        "subtopic": "Buffer Pool Exhaustion Bottlenecks",
        "question_type": "prediction",
        "skill_type": "reasoning",
        "quality_tier": "specialized",
        "expected_concepts": [
            "buffer pool hit ratio",
            "disk IOPS saturation",
            "read latency cliff",
            "dirty page flushing queue",
            "connection pool exhaustion"
        ],
        "common_mistakes": [
            "Assuming latency increases linearly rather than exponentially when memory cache thresholds are crossed",
            "Overlooking that slow disk queries hold database locks and connections longer, cascading into pool exhaustion",
            "Focusing solely on CPU utilization when disk I/O wait (iowait) is the true bottleneck"
        ],
        "ideal_answer_points": [
            "Memory access is nanosecond-scale while SSD/disk reads are millisecond-scale (orders of magnitude difference)",
            "A drop from 99% to 60% hit ratio means 40x more read requests must hit physical disk, rapidly saturating disk IOPS limits",
            "Worker threads block on disk I/O wait, causing connection pool exhaustion and query queue build-up",
            "Throughput collapses and p99 latency spikes dramatically across all transactional workloads"
        ],
        "prerequisites": [
            "System performance metrics",
            "Database memory tuning"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "easy",
        "question": "How do document stores like MongoDB differ from relational databases in schema flexibility, and when is an embedded document pattern preferred over referencing foreign keys?",
        "topic": "NoSQL & Distributed Storage Paradigms",
        "subtopic": "Document Databases and Embedding",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "document store",
            "MongoDB",
            "schema-on-read",
            "embedded documents",
            "referencing vs embedding",
            "atomic document updates"
        ],
        "common_mistakes": [
            "Embedding unbounded growing lists (e.g. log events or comments) inside a single document exceeding size limits",
            "Thinking document databases eliminate the need for schema planning",
            "Using embedding when entities are updated independently by different services"
        ],
        "ideal_answer_points": [
            "Document stores persist semi-structured JSON/BSON documents with polymorphic schemas",
            "Embedding stores related sub-entities within the parent document, allowing retrieval in a single atomic disk read without joins",
            "Embedding is ideal for 1-to-few bounded relationships accessed together (e.g. user billing address)",
            "Referencing is preferred for 1-to-many unbounded relationships, shared entities, or frequently mutated standalone data"
        ],
        "prerequisites": [
            "Data modeling basics"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "medium",
        "question": "Compare wide-column family stores like Apache Cassandra with relational databases. How does Cassandra's peer-to-peer ring architecture achieve high write availability without a single point of failure?",
        "topic": "NoSQL & Distributed Storage Paradigms",
        "subtopic": "Cassandra Peer-to-Peer Ring",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "core",
        "expected_concepts": [
            "wide-column store",
            "Cassandra",
            "peer-to-peer masterless",
            "consistent hashing ring",
            "coordinator node",
            "gossip protocol"
        ],
        "common_mistakes": [
            "Thinking Cassandra supports arbitrary ad-hoc SQL joins and secondary index queries efficiently",
            "Assuming masterless architecture eliminates network partition inconsistencies",
            "Modeling tables in Cassandra before finalizing access query patterns"
        ],
        "ideal_answer_points": [
            "Cassandra uses a masterless peer-to-peer ring where every node is equal; any node can act as a request coordinator",
            "Partition keys are hashed onto the consistent ring to locate replica storage nodes",
            "Gossip protocol continuously shares node membership and cluster health state without a centralized controller",
            "Optimized for extreme write throughput and linear horizontal scalability without single points of failure"
        ],
        "prerequisites": [
            "Distributed systems",
            "NoSQL architectures"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "medium",
        "question": "What is the CAP theorem, and how do systems like DynamoDB or Cassandra let engineers tune consistency levels (e.g., quorum reads and writes) to balance latency against strong consistency?",
        "topic": "NoSQL & Distributed Storage Paradigms",
        "subtopic": "CAP Theorem and Tunable Consistency",
        "question_type": "tradeoff",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "core",
        "expected_concepts": [
            "CAP theorem",
            "Consistency vs Availability",
            "Partition tolerance",
            "tunable consistency",
            "Quorum (R + W > N)"
        ],
        "common_mistakes": [
            "Claiming a system can choose Consistency and Availability (CA) in a distributed network where partitions are inevitable",
            "Thinking eventual consistency means data will be corrupted or permanently lost",
            "Not understanding that Quorum reads and writes provide strong consistency guarantees"
        ],
        "ideal_answer_points": [
            "CAP: under a network partition (P), a distributed system must choose between Consistency (C) or Availability (A)",
            "Partition tolerance is non-negotiable in real-world networks; systems are effectively CP or AP",
            "Tunable consistency formula: if R (read replicas) + W (write replicas) > N (replication factor), reads overlap with writes guaranteeing strong consistency",
            "Lower consistency levels (e.g. ONE or LOCAL_ONE) yield minimal latency and maximum availability"
        ],
        "prerequisites": [
            "Distributed systems theory",
            "Replication fundamentals"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "hard",
        "question": "When would you choose a graph database like Neo4j over a relational database with recursive Common Table Expressions (CTEs) for querying deep hierarchical or social network relationships?",
        "topic": "NoSQL & Distributed Storage Paradigms",
        "subtopic": "Graph Databases vs Relational CTEs",
        "question_type": "design",
        "skill_type": "design",
        "quality_tier": "advanced",
        "expected_concepts": [
            "graph database",
            "Neo4j",
            "index-free adjacency",
            "recursive CTEs",
            "variable-length path traversal"
        ],
        "common_mistakes": [
            "Using a graph database for simple tabular CRUD reporting where relational SQL excels",
            "Assuming recursive CTEs scale to arbitrary traversal depths without exponential join explosion",
            "Neglecting that graph databases have steeper operational learning curves and less mature tooling"
        ],
        "ideal_answer_points": [
            "Relational recursive CTEs perform join-table lookups at each traversal step, resulting in exponential computational slowdowns at depth > 3",
            "Graph databases implement index-free adjacency: nodes point directly to adjacent neighbor nodes in memory pointers",
            "Traversal time in graph databases is proportional to the size of the subgraph traversed, independent of overall graph database size",
            "Ideal for fraud detection networks, knowledge graphs, recommendation engines, and social graph traversals"
        ],
        "prerequisites": [
            "Graph theory",
            "SQL recursive queries"
        ]
    },
    {
        "category": "Databases",
        "difficulty": "hard",
        "question": "How do time-series databases like TimescaleDB or InfluxDB optimize data compression, downsampling, and retention policies compared to general-purpose relational engines?",
        "topic": "NoSQL & Distributed Storage Paradigms",
        "subtopic": "Time-Series Storage Optimization",
        "question_type": "scenario",
        "skill_type": "reasoning",
        "quality_tier": "specialized",
        "expected_concepts": [
            "time-series database",
            "hypertables",
            "columnar compression",
            "delta-of-delta encoding",
            "Gorilla compression",
            "retention policies"
        ],
        "common_mistakes": [
            "Using generic B-tree indexed relational tables for high-frequency IoT telemetry without chunking",
            "Writing expensive manual cron scripts to delete old time-series rows one by one",
            "Ignoring the write-amplification penalty of random row-oriented storage on append-only streams"
        ],
        "ideal_answer_points": [
            "Partition data automatically into time-and-space chunks (hypertables) to keep active write indexes in RAM",
            "Apply specialized columnar compression algorithms: delta-of-delta for timestamps and XOR Gorilla compression for floating-point values",
            "Continuous aggregate views automatically downsample raw high-frequency data into hourly or daily rollup summaries",
            "Data retention policies drop entire expired time chunks via metadata operations without row-level DELETE overhead"
        ],
        "prerequisites": [
            "Time-series data architecture",
            "Data compression"
        ]
    },
    {
        "id": 12,
        "category": "System Design",
        "difficulty": "medium",
        "question": "What is the difference between horizontal and vertical scaling, and what challenges arise with horizontal scaling?",
        "topic": "Distributed Architecture & Scalability",
        "subtopic": "Scaling Strategies",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "core",
        "expected_concepts": [
            "horizontal scaling",
            "vertical scaling",
            "scale up vs scale out",
            "state management",
            "network latency",
            "data partitioning"
        ],
        "common_mistakes": [
            "Claiming horizontal scaling is always strictly better without acknowledging distributed complexity",
            "Overlooking stateful component challenges like distributed database transactions",
            "Ignoring the hard physical ceiling on vertical scaling"
        ],
        "ideal_answer_points": [
            "Vertical scaling (scale up) adds CPU/RAM to a single machine; bounded by hardware limits and single point of failure",
            "Horizontal scaling (scale out) adds more machines; theoretically unlimited scaling potential",
            "Challenges of horizontal scaling: distributed data consistency, load balancing, network partitioning, and state synchronization",
            "Stateless application tiers simplify horizontal scaling behind load balancers"
        ],
        "prerequisites": [
            "Client-server architecture",
            "Basic networking"
        ]
    },
    {
        "id": 13,
        "category": "System Design",
        "difficulty": "hard",
        "question": "Explain how caching strategies like Cache-Aside, Write-Through, and Write-Back work.",
        "topic": "Caching, Buffering & Message Queues",
        "subtopic": "Caching Strategies & Invalidation",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "advanced",
        "expected_concepts": [
            "Cache-Aside",
            "Write-Through",
            "Write-Back (Write-Behind)",
            "cache invalidation",
            "eventual consistency",
            "data loss risk"
        ],
        "common_mistakes": [
            "Confusing Write-Through with Write-Back regarding write latency and durability",
            "Failing to account for race conditions during Cache-Aside updates",
            "Assuming caching eliminates the need for database index optimization"
        ],
        "ideal_answer_points": [
            "Cache-Aside (Lazy Loading): application queries cache; on miss loads from DB and puts in cache. Low write cost, risk of stale reads",
            "Write-Through: data written synchronously to cache and DB simultaneously. Consistent data, higher write latency",
            "Write-Back: data written to cache immediately, asynchronously flushed to DB in batches. Very low write latency, risk of data loss on cache crash",
            "Tradeoffs in eviction policies (LRU/LFU) and cache invalidation complexity"
        ],
        "prerequisites": [
            "In-memory key-value stores",
            "Data persistence concepts"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "easy",
        "question": "What is a stateless service architecture, and why is keeping application servers stateless essential for horizontal auto-scaling behind a load balancer?",
        "topic": "Distributed Architecture & Scalability",
        "subtopic": "Stateless Architecture",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "stateless architecture",
            "session state externalization",
            "horizontal auto-scaling",
            "load balancing",
            "ephemeral compute"
        ],
        "common_mistakes": [
            "Storing session state in local server memory or local file systems",
            "Confusing stateless compute with having no database or cache anywhere in the system",
            "Relying on sticky sessions as a substitute for true statelessness"
        ],
        "ideal_answer_points": [
            "Stateless services treat every incoming request independently without depending on local server memory from prior calls",
            "Session and user state is offloaded to external shared stores (e.g. Redis, relational databases, or JWTs)",
            "Enables traffic to be routed to any instance behind a load balancer with equal validity",
            "Allows horizontal auto-scalers to rapidly spin up or terminate instances without dropping user sessions"
        ],
        "prerequisites": [
            "Web architecture basics"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "medium",
        "question": "Design a URL shortening service like TinyURL. Walk through API design, short hash generation strategies (Base62 vs hashing), database schema, and handling collision resolution.",
        "topic": "Distributed Architecture & Scalability",
        "subtopic": "URL Shortener Architecture",
        "question_type": "design",
        "skill_type": "design",
        "quality_tier": "core",
        "expected_concepts": [
            "Base62 encoding",
            "MD5/SHA-256 truncation",
            "auto-increment ID generator (Snowflake)",
            "redirect status codes (301 vs 302)",
            "read-heavy caching"
        ],
        "common_mistakes": [
            "Using simple MD5 hashing and relying on retry loops for hash collision resolution",
            "Choosing 301 Permanent Redirect without realizing it bypasses click analytics via browser caching",
            "Using a single relational database without an in-memory caching tier for 100:1 read ratios"
        ],
        "ideal_answer_points": [
            "APIs: POST /api/shorten (accepts long URL, returns short URL) and GET /{shortCode} (redirects to destination)",
            "Encoding: Base62 encoding on unique distributed 64-bit IDs (Snowflake/Ticket service) guarantees unique 7-character short codes without collisions",
            "HTTP 302 (Found) allows capturing click analytics on each visit; 301 caches in client browser reducing server hits",
            "Cache hot URLs in Redis (LRU policy); persist mappings in NoSQL key-value store or partitioned relational table"
        ],
        "prerequisites": [
            "Distributed ID generation",
            "HTTP status codes"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "medium",
        "question": "Compare microservices architecture with monolithic architecture. What organizational and operational overheads (such as network latency, distributed tracing, and CI/CD complexity) must be considered before decomposing a monolith?",
        "topic": "Distributed Architecture & Scalability",
        "subtopic": "Monolith vs Microservices",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "core",
        "expected_concepts": [
            "microservices vs monolith",
            "network boundary latency",
            "distributed tracing",
            "independent deployments",
            "data consistency"
        ],
        "common_mistakes": [
            "Believing microservices solve internal code design problems automatically",
            "Ignoring the substantial operational maturity required (service mesh, Kubernetes, CI/CD pipelines)",
            "Adopting microservices before establishing clear bounded context domain boundaries"
        ],
        "ideal_answer_points": [
            "Monoliths offer single codebase simplicity, atomic local transactions, simple debugging, and zero inter-service network latency",
            "Microservices enable independent deployment cycles, language heterogeneity, and fault boundary isolation across autonomous teams",
            "Operational costs: distributed network failures, serialization overhead, complex distributed transactions (Sagas), and end-to-end tracing requirements",
            "Decomposition should follow domain-driven design (DDD) bounded contexts rather than arbitrary technical splits"
        ],
        "prerequisites": [
            "Software architecture patterns"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "hard",
        "question": "Design a real-time notification service that sends push notifications, SMS, and emails to 50 million active users. How do you handle user notification preferences, rate limits, and third-party vendor failures?",
        "topic": "Distributed Architecture & Scalability",
        "subtopic": "Real-Time Notification System",
        "question_type": "scenario",
        "skill_type": "design",
        "quality_tier": "advanced",
        "expected_concepts": [
            "message queues (Kafka/RabbitMQ)",
            "priority queues",
            "vendor rate limiting",
            "circuit breaker fallback",
            "preference evaluation",
            "idempotency keys"
        ],
        "common_mistakes": [
            "Sending notifications synchronously inside user-facing request threads",
            "Lacking idempotency, resulting in duplicate billing SMS or marketing emails on retries",
            "Ignoring upstream rate limits imposed by Apple APNs, Firebase FCM, or Twilio"
        ],
        "ideal_answer_points": [
            "Ingest notification events into distributed message queues (Kafka) partitioned by user_id",
            "Worker services validate user preferences (opt-outs, quiet hours) before assembling delivery payloads",
            "Dedicated channel worker pools (Push, Email, SMS) with rate-limiters enforcing external provider quotas",
            "Implement circuit breakers with secondary fallback providers (e.g. Twilio to MessageBird) and dead-letter queues for unrecoverable errors"
        ],
        "prerequisites": [
            "Distributed messaging",
            "Async workers"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "hard",
        "question": "How do circuit breaker patterns (like Resilience4j or Envoy) prevent cascading failures across microservices when a downstream dependency suffers degraded performance or outages?",
        "topic": "Distributed Architecture & Scalability",
        "subtopic": "Circuit Breaker Pattern",
        "question_type": "scenario",
        "skill_type": "reasoning",
        "quality_tier": "specialized",
        "expected_concepts": [
            "circuit breaker",
            "Closed, Open, Half-Open states",
            "cascading failures",
            "thread pool exhaustion",
            "graceful degradation"
        ],
        "common_mistakes": [
            "Setting timeout values too long, causing calling services to exhaust all HTTP connection pool threads while waiting",
            "Retrying immediately without exponential backoff or jitter, worsening downstream outage storms",
            "Failing to define fallback actions when circuit is open"
        ],
        "ideal_answer_points": [
            "Tracks failure rates and slow calls; transitions across Closed (normal), Open (fast fail), and Half-Open (trial canary) states",
            "In Open state, calls fail immediately without invoking the failing service, protecting caller threads from blocking",
            "Prevents resource exhaustion (threads, sockets, memory) across upstream services and prevents cascading cluster crashes",
            "Provides fallback responses (cached data, degraded stub responses) to maintain partial user functionality"
        ],
        "prerequisites": [
            "Microservice communication",
            "Fault tolerance patterns"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "easy",
        "question": "What is a Content Delivery Network (CDN), and how does edge caching reduce latency for static and media assets across geographically distributed users?",
        "topic": "Distributed Architecture & Scalability",
        "subtopic": "Content Delivery Networks",
        "question_type": "conceptual",
        "skill_type": "recall",
        "quality_tier": "core",
        "expected_concepts": [
            "CDN",
            "Points of Presence (PoPs)",
            "edge caching",
            "origin shielding",
            "TTL & cache purge"
        ],
        "common_mistakes": [
            "Thinking CDNs are only useful for static images and JavaScript files, ignoring dynamic edge compute (Cloudflare Workers)",
            "Forgetting to configure Cache-Control headers (e.g. max-age, stale-while-revalidate)",
            "Assuming CDN purge requests are globally instantaneous"
        ],
        "ideal_answer_points": [
            "CDNs deploy geographically distributed Points of Presence (PoPs) caching content near end users",
            "Terminates TLS connections at edge servers, reducing TCP/TLS handshake latency",
            "Serves cached static and streaming media directly from edge caches, shielding origin servers from massive traffic spikes",
            "Supports origin shielding and edge workers for dynamic routing, A/B testing, and DDoS mitigation"
        ],
        "prerequisites": [
            "HTTP caching",
            "DNS fundamentals"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "easy",
        "question": "What is the difference between strong consistency and eventual consistency in distributed data stores, and what user experience compromises does eventual consistency introduce?",
        "topic": "Data Consistency & Storage Pipelines",
        "subtopic": "Strong vs Eventual Consistency",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "strong consistency",
            "eventual consistency",
            "linearizability",
            "replication latency",
            "user experience tradeoffs"
        ],
        "common_mistakes": [
            "Assuming eventual consistency implies permanent data inconsistency or corruption",
            "Believing strong consistency can be achieved without increasing write latency",
            "Ignoring user interface mitigation patterns (optimistic UI updates)"
        ],
        "ideal_answer_points": [
            "Strong consistency guarantees any read returns the latest committed write (linearizability) across all nodes",
            "Eventual consistency guarantees all replicas converge to the same value given no new updates, but intermediate reads may be stale",
            "Strong consistency incurs higher write latency and reduced availability during network partitions",
            "UX compromises: stale view counts, temporary out-of-order comments, or needing explicit read-your-writes guarantees"
        ],
        "prerequisites": [
            "Distributed systems concepts"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "medium",
        "question": "Explain the Saga pattern for managing distributed transactions across microservices. How do choreography-based sagas compare with orchestration-based sagas when handling compensating transactions?",
        "topic": "Data Consistency & Storage Pipelines",
        "subtopic": "Saga Pattern for Distributed Transactions",
        "question_type": "scenario",
        "skill_type": "reasoning",
        "quality_tier": "core",
        "expected_concepts": [
            "Saga pattern",
            "compensating transactions",
            "choreography (event-driven)",
            "orchestration (central orchestrator)",
            "forward vs backward recovery"
        ],
        "common_mistakes": [
            "Thinking Sagas provide automatic transaction rollback like local ACID databases",
            "Overlooking that compensating transactions can also fail and require idempotent retry loops",
            "Allowing cyclic dependency deadlock in choreography-based sagas with complex workflows"
        ],
        "ideal_answer_points": [
            "A Saga coordinates a series of local database transactions across multiple microservices",
            "If a local step fails, the saga executes compensating transactions in reverse order to semantically undo changes",
            "Choreography: services react to domain events via message brokers; decentralized and simple for small workflows, but hard to trace at scale",
            "Orchestration: a dedicated orchestrator service explicitly issues command messages and tracks workflow state; centralized and auditable"
        ],
        "prerequisites": [
            "Microservice architecture",
            "Distributed transactions"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "hard",
        "question": "How does an append-only event sourcing architecture differ from standard CRUD persistence, and how do you use CQRS (Command Query Responsibility Segregation) to maintain high-performance read models?",
        "topic": "Data Consistency & Storage Pipelines",
        "subtopic": "Event Sourcing and CQRS",
        "question_type": "design",
        "skill_type": "design",
        "quality_tier": "advanced",
        "expected_concepts": [
            "event sourcing",
            "append-only event log",
            "CQRS",
            "materialized projections",
            "replaying events",
            "eventual consistency"
        ],
        "common_mistakes": [
            "Thinking event sourcing means querying the raw event stream for every user read request",
            "Ignoring event schema evolution and versioning (upcasting events)",
            "Underestimating projection rebuild times without periodic state snapshots"
        ],
        "ideal_answer_points": [
            "Event sourcing stores all state changes as an immutable append-only sequence of domain events rather than mutating current row values",
            "Provides a complete audit trail, temporal time-travel debugging, and historical analytics out of the box",
            "CQRS separates writes (Commands) from reads (Queries); projectors asynchronously consume events to build denormalized read-optimized materialized views",
            "State can be reconstructed by replaying events from genesis or from periodic snapshot checkpoints"
        ],
        "prerequisites": [
            "Data modeling",
            "Domain-driven design"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "hard",
        "question": "Design an idempotency mechanism for a financial payments API to guarantee that network retries never charge a customer twice. Detail token storage, lock acquisition, and response caching.",
        "topic": "Data Consistency & Storage Pipelines",
        "subtopic": "Payment API Idempotency",
        "question_type": "scenario",
        "skill_type": "design",
        "quality_tier": "specialized",
        "expected_concepts": [
            "idempotency key",
            "distributed lock",
            "atomic insert",
            "state machine",
            "response caching",
            "Stripe idempotency pattern"
        ],
        "common_mistakes": [
            "Checking if idempotency key exists without locking, allowing concurrent duplicate requests to slip past",
            "Caching only error responses rather than full successful payment receipt payloads",
            "Setting idempotency key TTL too short, allowing delayed network retries to process duplicates"
        ],
        "ideal_answer_points": [
            "Client generates a unique UUID (Idempotency-Key header) for the payment intent",
            "Server attempts an atomic insert into an idempotency table or Redis distributed lock (SET NX EX)",
            "If key exists with 'in-progress' status, return 409 Conflict or wait; if 'completed', return the cached prior response payload immediately",
            "Wrap payment execution in an atomic transaction; update idempotency record status to 'completed' with serialized response on commit"
        ],
        "prerequisites": [
            "REST API design",
            "Distributed locking"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "easy",
        "question": "Compare HTTP/1.1, HTTP/2, and HTTP/3 (QUIC) in terms of connection multiplexing, head-of-line blocking, and handshake latency.",
        "topic": "Networking, Protocols & Load Balancing",
        "subtopic": "HTTP Protocols Evolution",
        "question_type": "comparison",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "HTTP/1.1",
            "HTTP/2",
            "HTTP/3 (QUIC)",
            "head-of-line blocking",
            "TCP vs UDP",
            "TLS 1.3 handshake"
        ],
        "common_mistakes": [
            "Thinking HTTP/2 eliminates all head-of-line blocking (it solves application-layer HOL, but TCP-layer packet loss still blocks all streams)",
            "Believing HTTP/3 uses TCP instead of UDP",
            "Assuming HTTP/2 multiplexing requires multiple TCP connections"
        ],
        "ideal_answer_points": [
            "HTTP/1.1: sequential requests per TCP connection; suffers from application-layer head-of-line blocking, requiring browser domain sharding",
            "HTTP/2: multiplexes multiple logical streams over a single TCP connection with binary framing and HPACK header compression",
            "HTTP/2 TCP drawback: single lost packet stalls all streams in the TCP window",
            "HTTP/3: uses QUIC over UDP; independent streams eliminate TCP-level head-of-line blocking and combine transport/TLS handshakes into 0-RTT/1-RTT"
        ],
        "prerequisites": [
            "Computer networking fundamentals",
            "OSI model"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "medium",
        "question": "Compare Layer 4 (TCP/UDP) load balancers with Layer 7 (HTTP/HTTPS) load balancers. When is L7 routing necessary for path-based routing or SSL termination?",
        "topic": "Networking, Protocols & Load Balancing",
        "subtopic": "Layer 4 vs Layer 7 Load Balancing",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "core",
        "expected_concepts": [
            "Layer 4 (L4) load balancer",
            "Layer 7 (L7) load balancer",
            "TCP packet routing",
            "HTTP inspection",
            "SSL/TLS termination",
            "path-based routing"
        ],
        "common_mistakes": [
            "Thinking L4 load balancers can inspect HTTP cookies or URL paths",
            "Assuming L7 load balancers have identical packet throughput to L4 balancers",
            "Neglecting CPU overhead of terminating TLS at L7 load balancers"
        ],
        "ideal_answer_points": [
            "L4 operates at transport layer (IP/Port); routes raw TCP/UDP packets without decrypting or inspecting payload; extremely fast with minimal CPU overhead",
            "L7 operates at application layer (HTTP/HTTPS); terminates TLS, parses HTTP headers, cookies, and URI paths",
            "L7 is required for URL path routing (/api vs /static), gRPC routing, header-based canary deployments, and authentication inspection",
            "High-scale architectures combine both: L4 front-ends distribute raw packets to pools of scalable L7 reverse proxies (e.g. Nginx/Envoy)"
        ],
        "prerequisites": [
            "Networking layers",
            "Reverse proxies"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "medium",
        "question": "When designing real-time interactive applications like a live chat or stock price ticker, compare WebSockets, Server-Sent Events (SSE), and Long Polling in terms of bidirectional capability, server overhead, and protocol complexity.",
        "topic": "Networking, Protocols & Load Balancing",
        "subtopic": "Real-Time Communication Protocols",
        "question_type": "scenario",
        "skill_type": "application",
        "quality_tier": "core",
        "expected_concepts": [
            "WebSockets",
            "Server-Sent Events (SSE)",
            "Long Polling",
            "full-duplex vs unidirectional",
            "HTTP/2 push",
            "connection persistence"
        ],
        "common_mistakes": [
            "Using WebSockets for strictly server-to-client streaming where SSE provides simpler HTTP-compatible streaming with automatic reconnection",
            "Assuming Long Polling has lower server overhead than persistent WebSocket connections",
            "Ignoring proxy/firewall traversal challenges with custom binary WebSocket protocols"
        ],
        "ideal_answer_points": [
            "WebSockets: full-duplex bidirectional communication over single persistent TCP socket; ideal for real-time multiplayer gaming and interactive chat",
            "Server-Sent Events (SSE): unidirectional server-to-client streaming over standard HTTP; built-in reconnection, simple text-based protocol; ideal for stock tickers and LLM token streaming",
            "Long Polling: client holds HTTP request open until data arrives then immediately reconnects; fallback mechanism with high header overhead and connection churn",
            "WebSockets require sticky sessions or Redis pub/sub backplanes across horizontally scaled servers"
        ],
        "prerequisites": [
            "HTTP protocol",
            "Socket programming"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "hard",
        "question": "How does consistent hashing with virtual nodes work in a distributed load balancer or caching ring, and how does it prevent mass cache invalidation when nodes are added or removed?",
        "topic": "Networking, Protocols & Load Balancing",
        "subtopic": "Consistent Hashing and Virtual Nodes",
        "question_type": "design",
        "skill_type": "design",
        "quality_tier": "advanced",
        "expected_concepts": [
            "consistent hashing",
            "hash ring",
            "virtual nodes (vnodes)",
            "rebalancing overhead",
            "hotspot prevention",
            "K/N keys migrated"
        ],
        "common_mistakes": [
            "Using simple modulo hashing (hash(key) % N) where changing N forces almost 100% of keys to remap",
            "Omitting virtual nodes, causing non-uniform key distribution and server hotspots",
            "Assuming consistent hashing eliminates all replication requirements"
        ],
        "ideal_answer_points": [
            "Map servers and keys onto a circular 32-bit or 64-bit integer hash space (hash ring)",
            "A key is stored on the first server node encountered moving clockwise on the ring",
            "Adding or removing a server node only migrates keys from its immediate neighbor (approximately K/N keys moved, where K is total keys and N is servers)",
            "Virtual nodes assign each physical server multiple points across the ring, evening out key distribution and spreading failover load evenly"
        ],
        "prerequisites": [
            "Hash functions",
            "Distributed caching"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "hard",
        "question": "What is gRPC, how does it leverage Protocol Buffers and HTTP/2 multiplexing, and what are the tradeoffs of using gRPC over REST with JSON for inter-service communication?",
        "topic": "Networking, Protocols & Load Balancing",
        "subtopic": "gRPC vs REST with Protobuf",
        "question_type": "scenario",
        "skill_type": "reasoning",
        "quality_tier": "specialized",
        "expected_concepts": [
            "gRPC",
            "Protocol Buffers",
            "HTTP/2 framing",
            "binary serialization",
            "streaming RPCs",
            "schema evolution"
        ],
        "common_mistakes": [
            "Assuming gRPC works seamlessly in standard browser frontends without gRPC-Web proxy translation",
            "Believing Protobuf fields can be renumbered without breaking backward compatibility",
            "Using gRPC for public external consumer APIs where REST/JSON is the universal standard"
        ],
        "ideal_answer_points": [
            "gRPC uses Protocol Buffers (strongly typed binary serialization) over HTTP/2 persistent multiplexed connections",
            "Drastically reduces payload size and CPU serialization/deserialization overhead compared to textual JSON parsing",
            "Supports streaming patterns: unary, server streaming, client streaming, and bidirectional streaming",
            "Tradeoffs: strict contract schemas and high performance make it ideal for internal microservices, but human readability is lost and web browser support requires proxies"
        ],
        "prerequisites": [
            "RPC frameworks",
            "Binary serialization"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "easy",
        "question": "What is the difference between cache stampede (thundering herd) and cache penetration, and how do mutex locks or probabilistic early expiration prevent cache stampedes?",
        "topic": "Caching, Buffering & Message Queues",
        "subtopic": "Cache Stampede and Penetration",
        "question_type": "conceptual",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "cache stampede (thundering herd)",
            "cache penetration",
            "mutex locking (single-flight)",
            "probabilistic early expiration (XFetch)",
            "Bloom filters"
        ],
        "common_mistakes": [
            "Confusing cache stampede (popular key expires) with cache penetration (querying non-existent keys repeatedly)",
            "Setting identical TTLs on thousands of related keys causing simultaneous mass expiration",
            "Believing adding more database read replicas solves a complete cache stampede"
        ],
        "ideal_answer_points": [
            "Cache stampede: popular key expires; thousands of concurrent requests miss and simultaneously slam the database to recompute the same value",
            "Cache penetration: requests query keys that never exist in database; cache misses continuously, sending all requests to database; solved with Bloom filters or caching null sentinels",
            "Mutex lock (single-flight): first request acquires lock to compute and populate cache; subsequent requests wait and read the refreshed cache",
            "Probabilistic early expiration (XFetch algorithm): worker probabilistically recomputes the cache value before actual expiration based on compute delta and time remaining"
        ],
        "prerequisites": [
            "Caching fundamentals"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "medium",
        "question": "Compare message queues like RabbitMQ (AMQP push-based broker) with distributed commit logs like Apache Kafka (pull-based partition log) in message ordering, throughput, and consumer offsets.",
        "topic": "Caching, Buffering & Message Queues",
        "subtopic": "RabbitMQ vs Apache Kafka",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "core",
        "expected_concepts": [
            "message queue vs commit log",
            "RabbitMQ AMQP",
            "Apache Kafka partitions",
            "push vs pull model",
            "message retention and replay",
            "consumer offset management"
        ],
        "common_mistakes": [
            "Using Kafka as a transient task queue requiring individual message acknowledgment and deletion",
            "Expecting global message ordering in Kafka across multiple partitions without single-partition pinning",
            "Assuming RabbitMQ supports replaying historical messages from days ago"
        ],
        "ideal_answer_points": [
            "RabbitMQ: smart broker, dumb consumer; messages pushed to consumers and deleted upon acknowledgment; advanced routing exchanges; best for complex task queues",
            "Kafka: dumb broker, smart consumer; append-only partitioned commit log; messages retained for configurable retention period allowing replay; high sequential throughput",
            "Ordering: RabbitMQ maintains queue FIFO order; Kafka guarantees strict ordering only within individual partitions",
            "Consumer offsets: RabbitMQ tracks per-message delivery state; Kafka consumers track simple numeric offset pointers into the log"
        ],
        "prerequisites": [
            "Message queuing",
            "Streaming architectures"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "medium",
        "question": "Design a rate limiter for a public API that supports 10,000 requests per minute per API key. Compare the Token Bucket algorithm, Leaky Bucket, and Sliding Window Log using Redis.",
        "topic": "Caching, Buffering & Message Queues",
        "subtopic": "API Rate Limiter Algorithms",
        "question_type": "scenario",
        "skill_type": "design",
        "quality_tier": "core",
        "expected_concepts": [
            "Token Bucket",
            "Leaky Bucket",
            "Sliding Window Log",
            "Sliding Window Counter",
            "Redis Lua scripts",
            "HTTP 429 Too Many Requests"
        ],
        "common_mistakes": [
            "Using Fixed Window counters that allow double the rate limit across window boundary edges",
            "Storing individual request timestamps in Redis for Sliding Window Log without considering unbounded memory growth",
            "Executing non-atomic multi-step Redis reads and writes without Lua scripts or atomic transactions"
        ],
        "ideal_answer_points": [
            "Token Bucket: tokens refill at fixed rate; accommodates traffic bursts up to bucket capacity; memory efficient (stores timestamp and token count)",
            "Leaky Bucket: requests enter queue and leak out at smooth constant rate; eliminates bursts, but drops or queues requests",
            "Sliding Window Counter: blends previous and current window counts using weighted overlap; low memory and prevents boundary edge spikes",
            "Implement via Redis atomic Lua script returning remaining tokens and Retry-After header with HTTP 429 status code"
        ],
        "prerequisites": [
            "Redis fundamentals",
            "Rate limiting algorithms"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "hard",
        "question": "How do you guarantee exactly-once processing semantics in a streaming pipeline using Apache Kafka and Flink, and why is end-to-end exactly-once fundamentally idempotent at-least-once delivery with deduplication?",
        "topic": "Caching, Buffering & Message Queues",
        "subtopic": "Exactly-Once Streaming Semantics",
        "question_type": "scenario",
        "skill_type": "design",
        "quality_tier": "advanced",
        "expected_concepts": [
            "exactly-once semantics (EOS)",
            "at-least-once with idempotency",
            "Kafka transactional producer",
            "Flink Chandy-Lamport checkpointing",
            "Two-Phase Commit sink"
        ],
        "common_mistakes": [
            "Believing exactly-once means physical network packets are never duplicated during transmission",
            "Neglecting that non-transactional downstream sinks (e.g. standard REST APIs) cannot undo side effects on rollback",
            "Confusing stream processing exactly-once with end-to-end distributed system exactly-once"
        ],
        "ideal_answer_points": [
            "Physical packet duplication is inevitable in distributed networks; 'exactly-once' means effects on state are applied exactly once",
            "Kafka transactional API writes records and commit markers atomically across partitions",
            "Flink uses distributed Chandy-Lamport aligned checkpointing to capture consistent operator state snapshots",
            "End-to-end EOS requires two-phase commit sinks (TwoPhaseCommitSinkFunction) tying sink commits to Flink checkpoint completions, or deterministic idempotent writes"
        ],
        "prerequisites": [
            "Stream processing",
            "Distributed consensus"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "hard",
        "question": "In a high-throughput message processing pipeline, consumers begin lagging significantly behind the queue. Walk through how you diagnose whether the issue is poison-pill messages, slow database writes, or consumer thread starvation.",
        "topic": "Caching, Buffering & Message Queues",
        "subtopic": "Message Queue Lag Troubleshooting",
        "question_type": "debugging",
        "skill_type": "debugging",
        "quality_tier": "advanced",
        "expected_concepts": [
            "consumer lag metrics",
            "poison pill messages",
            "dead-letter queue (DLQ)",
            "database write latency",
            "thread pool saturation",
            "rebalancing storms"
        ],
        "common_mistakes": [
            "Immediately scaling up consumer instances without verifying if partitions are already 1:1 with consumers",
            "Allowing a poison-pill message to block partition processing indefinitely in an infinite crash-restart loop",
            "Ignoring database connection pool exhaustion as the underlying root cause of worker backpressure"
        ],
        "ideal_answer_points": [
            "Check consumer group lag metrics per partition (e.g. kafka-consumer-groups) to see if lag is isolated to one partition or cluster-wide",
            "Poison pill: single partition stuck at offset with high worker crash rate; isolate via dead-letter queue (DLQ) after N retries",
            "Database bottleneck: correlate database write latency and connection pool wait times with consumer processing durations",
            "Thread starvation: profile consumer CPU/memory metrics and thread dumps to detect lock contention or thread exhaustion"
        ],
        "prerequisites": [
            "Kafka operations",
            "System metrics and profiling"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "easy",
        "question": "What are the three pillars of observability (Metrics, Logs, Traces), and how does distributed tracing with trace IDs and span IDs link a request across multiple microservices?",
        "topic": "Reliability, Observability & Fault Tolerance",
        "subtopic": "Observability Pillars and Distributed Tracing",
        "question_type": "conceptual",
        "skill_type": "recall",
        "quality_tier": "core",
        "expected_concepts": [
            "metrics",
            "structured logs",
            "distributed traces",
            "trace ID",
            "span ID",
            "W3C Trace Context",
            "OpenTelemetry"
        ],
        "common_mistakes": [
            "Thinking high log volume replaces the need for time-series metrics",
            "Not propagating trace headers (traceparent) across async message queues and external HTTP calls",
            "Writing unstructured text logs that cannot be indexed or aggregated efficiently"
        ],
        "ideal_answer_points": [
            "Metrics: aggregated numerical time-series (counters, gauges, histograms) for alerting and high-level health trends",
            "Logs: structured timestamped contextual events (JSON) detailing discrete execution events and errors",
            "Traces: end-to-end request lifecycle DAGs showing latency breakdowns across distributed network hops",
            "Trace ID globally identifies the request; Span IDs represent individual service operations; headers propagated via W3C Trace Context standard"
        ],
        "prerequisites": [
            "Microservice architecture",
            "Software observability"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "medium",
        "question": "Explain the bulkhead pattern in distributed systems. How does isolating thread pools or connection pools prevent one misbehaving client or endpoint from starving the entire service?",
        "topic": "Reliability, Observability & Fault Tolerance",
        "subtopic": "Bulkhead Pattern and Fault Isolation",
        "question_type": "scenario",
        "skill_type": "application",
        "quality_tier": "core",
        "expected_concepts": [
            "bulkhead pattern",
            "resource isolation",
            "thread pool partitioning",
            "connection pool starvation",
            "noisy neighbor protection"
        ],
        "common_mistakes": [
            "Using a single shared thread pool for both critical user traffic and slow external third-party integrations",
            "Setting thread pool queue sizes to unbounded lengths leading to memory exhaustion under latency spikes",
            "Assuming bulkheads eliminate the need for circuit breakers and timeouts"
        ],
        "ideal_answer_points": [
            "Named after ship bulkheads that prevent water in a punctured compartment from sinking the entire vessel",
            "Partition shared resources (thread pools, memory, database connection pools) by tenant, customer tier, or outbound integration",
            "If a slow downstream service causes thread exhaustion, only its dedicated pool exhausts, leaving other pools healthy",
            "Prevents noisy neighbor problems and protects core customer journeys from secondary feature degradation"
        ],
        "prerequisites": [
            "Concurrency",
            "Resilience engineering"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "medium",
        "question": "What is the difference between active-passive (hot standby) and active-active multi-region disaster recovery, and how do data synchronization costs and RPO/RTO targets influence the choice?",
        "topic": "Reliability, Observability & Fault Tolerance",
        "subtopic": "Multi-Region Disaster Recovery",
        "question_type": "tradeoff",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "core",
        "expected_concepts": [
            "active-passive",
            "active-active",
            "RPO (Recovery Point Objective)",
            "RTO (Recovery Time Objective)",
            "cross-region replication latency",
            "conflict resolution"
        ],
        "common_mistakes": [
            "Assuming active-active multi-region is simple to implement without solving multi-master database write conflicts",
            "Ignoring egress network data transfer costs for continuous cross-region data replication",
            "Setting RPO=0 expectation with asynchronous replication architectures"
        ],
        "ideal_answer_points": [
            "Active-Passive: primary region handles all traffic; secondary region receives replicated data and stands by; simpler to operate, lower cost, but higher RTO on failover",
            "Active-Active: all regions serve live traffic concurrently; near-zero RTO and highest availability, but requires multi-region data synchronization and conflict resolution (CRDTs or last-write-wins)",
            "RPO (Recovery Point Objective): maximum acceptable data loss duration; RTO (Recovery Time Objective): maximum acceptable downtime duration",
            "Choice is governed by compliance requirements, business downtime cost versus infrastructure complexity and network egress expenses"
        ],
        "prerequisites": [
            "Disaster recovery concepts",
            "High availability"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "hard",
        "question": "Design an automated health check and canary deployment pipeline that monitors error rates and latency in real time, automatically rolling back bad releases before affecting the entire fleet.",
        "topic": "Reliability, Observability & Fault Tolerance",
        "subtopic": "Canary Deployments and Automated Rollbacks",
        "question_type": "design",
        "skill_type": "design",
        "quality_tier": "advanced",
        "expected_concepts": [
            "canary deployment",
            "traffic routing (Envoy/Istio)",
            "SLO/SLI monitoring",
            "automated rollback",
            "liveness vs readiness probes"
        ],
        "common_mistakes": [
            "Deploying canary instances that share mutated database schemas incompatible with prior versions",
            "Rolling out canary traffic too fast before sufficient statistical sample size is gathered",
            "Using simple liveness health checks instead of deep readiness and business metric validation"
        ],
        "ideal_answer_points": [
            "Route small fraction (1-5%) of production traffic to canary pods using service mesh or weighted load balancer routing",
            "Continuously compare canary SLIs (p99 latency, HTTP 5xx error rate, business conversion) against baseline fleet over time window",
            "If metrics breach defined error budget thresholds, automated controller cuts traffic back to baseline and triggers alert",
            "If healthy, step traffic incrementally (10% -> 25% -> 50% -> 100%) using automated progressive delivery tools like Argo Rollouts or Flagger"
        ],
        "prerequisites": [
            "CI/CD pipelines",
            "Kubernetes networking"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "hard",
        "question": "How do consensus protocols like Raft elect a leader and replicate log entries across distributed nodes while surviving network partitions?",
        "topic": "Reliability, Observability & Fault Tolerance",
        "subtopic": "Raft Distributed Consensus",
        "question_type": "scenario",
        "skill_type": "reasoning",
        "quality_tier": "specialized",
        "expected_concepts": [
            "Raft consensus",
            "Leader, Follower, Candidate states",
            "heartbeats and randomized election timeouts",
            "log replication quorum",
            "term numbers",
            "network partitions"
        ],
        "common_mistakes": [
            "Thinking a disconnected minority partition can elect a leader and commit writes",
            "Confusing split-brain prevention with multi-leader write throughput",
            "Assuming Raft requires synchronized physical clocks (unlike Paxos variants or Spanner TrueTime)"
        ],
        "ideal_answer_points": [
            "Nodes transition between Follower, Candidate, and Leader states; randomized election timeouts prevent split-vote deadlocks",
            "Candidate requests votes with term number; requires majority approval (N/2 + 1) to become leader",
            "Leader appends entries to its log and sends AppendEntries RPCs to followers; entry is committed once replicated to a majority quorum",
            "During network partitions, the minority partition cannot achieve quorum, preventing stale leader commits and ensuring safety"
        ],
        "prerequisites": [
            "Distributed systems theory",
            "State machine replication"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "easy",
        "question": "Compare session-based authentication with stateful server sessions versus stateless JWT (JSON Web Token) authentication. What are the challenges in revoking JWTs before expiration?",
        "topic": "API & Security Architecture",
        "subtopic": "Session vs JWT Authentication",
        "question_type": "comparison",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "session cookies",
            "JWT (JSON Web Token)",
            "cryptographic signature",
            "token revocation",
            "refresh token pattern",
            "Redis blacklist"
        ],
        "common_mistakes": [
            "Storing sensitive passwords or PII inside unencrypted base64 JWT payload claims",
            "Assuming stateless JWTs can be immediately revoked without introducing centralized state (e.g. Redis blacklist)",
            "Using JWTs for long-lived sessions without short access token TTLs and refresh token rotation"
        ],
        "ideal_answer_points": [
            "Session auth: server stores session state in DB/Redis and issues random opaque session ID cookie; instant revocation via deletion, but requires server-side storage lookup on every request",
            "JWT auth: digitally signed self-contained token verified via public key or HMAC secret; stateless verification across services without DB lookups",
            "Revocation challenge: valid JWT cannot be invalidated before expiration without tracking an explicit revocation blacklist in a shared store",
            "Best practice: short-lived access JWTs (5-15 mins) paired with stateful, revocable refresh tokens stored in secure HttpOnly cookies"
        ],
        "prerequisites": [
            "Web security basics",
            "Authentication"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "medium",
        "question": "Design an API Gateway for a modern cloud application. What responsibilities should be centralized in the gateway (such as authentication, SSL termination, rate limiting, and request routing) versus delegated to downstream services?",
        "topic": "API & Security Architecture",
        "subtopic": "API Gateway Responsibilities",
        "question_type": "design",
        "skill_type": "design",
        "quality_tier": "core",
        "expected_concepts": [
            "API Gateway",
            "cross-cutting concerns",
            "SSL termination",
            "authentication/authorization",
            "rate limiting",
            "service discovery",
            "BFF pattern"
        ],
        "common_mistakes": [
            "Embedding business domain logic or database access inside the API Gateway layer",
            "Allowing the gateway to become a fragile monolithic single point of failure and team deployment bottleneck",
            "Failing to establish internal trust boundaries between gateway and backend services"
        ],
        "ideal_answer_points": [
            "Centralize cross-cutting concerns: SSL termination, edge rate-limiting, CORS handling, client authentication, and request tracing injection",
            "Route requests to internal services via service discovery, protocol translation (HTTP to gRPC), and request aggregation (BFF pattern)",
            "Delegate domain-specific business rules, fine-grained authorization, and database persistence to specialized downstream services",
            "Ensure high availability with horizontal scaling and resilient configuration reloading without dropping active traffic"
        ],
        "prerequisites": [
            "API design",
            "Cloud architecture"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "medium",
        "question": "How do you protect a distributed web application against common security threats including Cross-Site Scripting (XSS), Cross-Site Request Forgery (CSRF), and SQL Injection?",
        "topic": "API & Security Architecture",
        "subtopic": "Web Application Security Defenses",
        "question_type": "scenario",
        "skill_type": "application",
        "quality_tier": "core",
        "expected_concepts": [
            "SQL Injection",
            "XSS (Stored, Reflected)",
            "CSRF",
            "parameterized queries",
            "Content Security Policy (CSP)",
            "SameSite cookies",
            "anti-CSRF tokens"
        ],
        "common_mistakes": [
            "Relying on manual string sanitization or regex filtering rather than parameterized prepared statements for SQL",
            "Assuming HTTPS encryption protects against XSS or CSRF attacks",
            "Storing sensitive authentication tokens in browser localStorage vulnerable to XSS exfiltration"
        ],
        "ideal_answer_points": [
            "SQL Injection: strictly use parameterized queries and ORMs; never concatenate user input into SQL strings",
            "XSS: contextual output encoding, robust Content Security Policy (CSP) headers, and storing tokens in HttpOnly secure cookies to block JavaScript access",
            "CSRF: enforce SameSite=Lax/Strict cookie attributes and validate cryptographic anti-CSRF synchronizer tokens on state-changing requests (POST/PUT/DELETE)",
            "Conduct automated dependency scanning (Snyk/Dependabot) and input validation across all API boundaries"
        ],
        "prerequisites": [
            "OWASP Top 10",
            "Web application security"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "hard",
        "question": "How do OAuth 2.0 and OpenID Connect (OIDC) Authorization Code Flow with PKCE protect user credentials when authenticating single-page and mobile applications against third-party identity providers?",
        "topic": "API & Security Architecture",
        "subtopic": "OAuth 2.0 and OIDC with PKCE",
        "question_type": "scenario",
        "skill_type": "design",
        "quality_tier": "advanced",
        "expected_concepts": [
            "OAuth 2.0 vs OIDC",
            "Authorization Code Flow",
            "PKCE (Proof Key for Code Exchange)",
            "code_verifier and code_challenge",
            "client_secret limitations on public clients",
            "ID token vs Access token"
        ],
        "common_mistakes": [
            "Using deprecated Implicit Flow in modern single-page applications",
            "Shipping hardcoded client_secret in client-side JavaScript or mobile app binaries",
            "Confusing OAuth (authorization) with OpenID Connect (authentication and user identity)"
        ],
        "ideal_answer_points": [
            "Public clients (SPA, mobile) cannot securely protect a client_secret from decompilation or inspection",
            "PKCE generates dynamic code_verifier and code_challenge (SHA-256 hash) per login flow",
            "Authorization server stores code_challenge; client exchanges authorization code and raw code_verifier at token endpoint",
            "Prevents authorization code interception attacks without requiring a static client_secret on the client device"
        ],
        "prerequisites": [
            "Cryptography basics",
            "OAuth 2.0 protocol"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "hard",
        "question": "Design a secure secrets management and key rotation architecture for microservices running in multi-tenant cloud environments using HashiCorp Vault or AWS KMS.",
        "topic": "API & Security Architecture",
        "subtopic": "Secrets Management and Key Rotation",
        "question_type": "design",
        "skill_type": "design",
        "quality_tier": "specialized",
        "expected_concepts": [
            "secrets management",
            "HashiCorp Vault",
            "envelope encryption",
            "AWS KMS",
            "dynamic secrets",
            "automated key rotation",
            "least privilege IAM"
        ],
        "common_mistakes": [
            "Committing secrets to Git repositories or injecting raw credentials into Docker container image layers",
            "Using static database passwords that are never rotated across months or years",
            "Failing to implement audit logging on secret access events"
        ],
        "ideal_answer_points": [
            "Envelope encryption: KMS encrypts data encryption keys (DEKs) using a Customer Master Key (CMK) that never leaves hardware security modules (HSMs)",
            "HashiCorp Vault provides short-lived dynamic credentials for databases and cloud APIs, generated on-demand and revoked automatically upon lease expiry",
            "Authenticate pods via Kubernetes Service Account tokens tied to fine-grained least-privilege IAM roles",
            "Automated rotation policies rotate KMS keys and application secrets without downtime using dual-key validation windows"
        ],
        "prerequisites": [
            "Public key cryptography",
            "Cloud security architectures"
        ]
    },
    {
        "category": "System Design",
        "difficulty": "easy",
        "question": "Compare polling versus webhook architectures for notifying external clients about asynchronous job completion in B2B SaaS platforms.",
        "topic": "API & Security Architecture",
        "subtopic": "Polling vs Webhooks",
        "question_type": "comparison",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "core",
        "expected_concepts": [
            "polling vs webhooks",
            "push vs pull",
            "HMAC signature verification",
            "retry backoff",
            "dead-letter handling"
        ],
        "common_mistakes": [
            "Implementing webhooks without HMAC-SHA256 signature verification headers allowing spoofed payloads",
            "Failing to handle exponential backoff retries when client webhook endpoints return 5xx errors",
            "Allowing aggressive client short-polling to overwhelm API infrastructure"
        ],
        "ideal_answer_points": [
            "Polling: client periodically sends HTTP GET requests; simple to implement through client firewalls, but incurs high empty request overhead and notification latency",
            "Webhooks: server sends HTTP POST to registered client endpoint upon event completion; instantaneous delivery and zero polling traffic overhead",
            "Webhooks require signature validation (X-Hub-Signature HMAC), delivery retry queues with exponential backoff, and idempotent event IDs on the receiver",
            "Polling remains a valuable fallback if customer infrastructure cannot accept public inbound internet traffic"
        ],
        "prerequisites": [
            "REST APIs",
            "Event-driven architecture"
        ]
    },
    {
        "id": 14,
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "Describe a challenging technical bug or outage you diagnosed. What was your debugging methodology?",
        "topic": "Ownership, Failure & Accountability",
        "subtopic": "Incident Response & Debugging",
        "question_type": "experience",
        "skill_type": "reasoning",
        "quality_tier": "core",
        "expected_concepts": [
            "incident triage",
            "reproduction",
            "observability/logs/metrics",
            "root cause analysis",
            "post-mortem prevention"
        ],
        "common_mistakes": [
            "Focusing only on the symptom without explaining systematic diagnostic steps",
            "Blaming external vendors or infrastructure rather than demonstrating technical ownership",
            "Omitting preventative actions implemented to prevent recurrence"
        ],
        "ideal_answer_points": [
            "STAR framework: Situation, Task, Action, Result",
            "Structured isolation methodology: hypothesis formulation, metric/log analysis, binary search/bisect",
            "Prioritizing blast radius containment and service restoration before root-cause deep dive",
            "Actionable post-mortem learnings and automated preventative monitoring"
        ],
        "prerequisites": [
            "Production software development experience"
        ]
    },
    {
        "id": 15,
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "How do you handle disagreement with a teammate or lead regarding architectural decisions or code reviews?",
        "topic": "Conflict Resolution & Collaboration",
        "subtopic": "Technical Disagreements",
        "question_type": "conflict",
        "skill_type": "communication",
        "quality_tier": "core",
        "expected_concepts": [
            "data-driven decision making",
            "active listening",
            "disagree and commit",
            "empathy",
            "tradeoff evaluation"
        ],
        "common_mistakes": [
            "Portraying disagreement as personal conflict rather than engineering debate",
            "Refusing to compromise or commit once a team consensus is reached",
            "Relying on positional authority rather than benchmarks or objective tradeoffs"
        ],
        "ideal_answer_points": [
            "Grounding discussions in objective metrics, system requirements, and engineering principles",
            "Seeking to understand opposing architectural constraints and trade-offs",
            "Using prototypes, spike tickets, or benchmarks to resolve ambiguities",
            "Demonstrating 'disagree and commit' to keep project delivery unblocked"
        ],
        "prerequisites": [
            "Collaborative engineering team experience"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "Tell me about a time you noticed an engineering inefficiency or technical debt that was not assigned to you, took the initiative to fix it, and drove adoption across your team.",
        "topic": "Leadership & Initiative",
        "subtopic": "Proactive Technical Debt Reduction",
        "question_type": "leadership",
        "skill_type": "communication",
        "quality_tier": "core",
        "expected_concepts": [
            "proactivity",
            "technical debt",
            "stakeholder alignment",
            "team productivity",
            "developer experience (DevEx)"
        ],
        "common_mistakes": [
            "Rewriting code without communicating with teammates or understanding historical context",
            "Neglecting to measure or communicate the business/productivity impact of the improvement",
            "Leaving the new solution undocumented and unused"
        ],
        "ideal_answer_points": [
            "Identified a recurring bottleneck (e.g. flaky CI tests, slow builds, cumbersome local environment setup)",
            "Gathered data on time lost across the engineering team to justify the investment",
            "Built a working prototype or proof-of-concept during dedicated improvement time",
            "Documented the workflow, hosted a team demo, and tracked improved delivery velocity"
        ],
        "prerequisites": [
            "Engineering team collaboration"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "hard",
        "question": "Describe a situation where you had to lead a cross-functional technical project without formal managerial authority. How did you align conflicting priorities between product, design, and engineering?",
        "topic": "Leadership & Initiative",
        "subtopic": "Influence Without Authority",
        "question_type": "leadership",
        "skill_type": "reasoning",
        "quality_tier": "advanced",
        "expected_concepts": [
            "influence without authority",
            "cross-functional alignment",
            "negotiation",
            "transparent roadmapping",
            "empathy"
        ],
        "common_mistakes": [
            "Trying to mandate decisions without consensus or stakeholder buy-in",
            "Dismissing design or product concerns as unimportant technical details",
            "Failing to establish shared definitions of success across departments"
        ],
        "ideal_answer_points": [
            "Established clear shared project goals aligned with overarching business objectives",
            "Facilitated structured RFC discussions and trade-off matrices where all disciplines voiced constraints",
            "Maintained transparent milestones, status dashboards, and unblocked cross-team dependencies",
            "Built trust through active listening, follow-through, and acknowledging peer contributions"
        ],
        "prerequisites": [
            "Cross-functional project leadership"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "easy",
        "question": "How do you onboard and mentor a junior engineer or new teammate to help them become productive and confident in a complex codebase?",
        "topic": "Leadership & Initiative",
        "subtopic": "Junior Mentorship and Onboarding",
        "question_type": "experience",
        "skill_type": "communication",
        "quality_tier": "core",
        "expected_concepts": [
            "mentorship",
            "onboarding checklist",
            "pair programming",
            "psychological safety",
            "incremental task delegation"
        ],
        "common_mistakes": [
            "Handing over documentation and leaving the mentee isolated without check-ins",
            "Solving problems for the mentee rather than guiding them with Socratic questions",
            "Overwhelming the new engineer with high-context complex tickets on week one"
        ],
        "ideal_answer_points": [
            "Created a structured 30-60-90 day onboarding roadmap with starter 'good first issues'",
            "Conducted regular pair-programming sessions and daily informal check-ins",
            "Fostered psychological safety by encouraging questions and normalizing knowledge gaps",
            "Guided code reviews with positive reinforcement and detailed architectural rationale"
        ],
        "prerequisites": [
            "Team collaboration",
            "Mentoring"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "Tell me about a time you championed adopting a new tool, framework, or process that faced initial skepticism from your team. How did you build consensus?",
        "topic": "Leadership & Initiative",
        "subtopic": "Technology Adoption and Consensus",
        "question_type": "leadership",
        "skill_type": "reasoning",
        "quality_tier": "advanced",
        "expected_concepts": [
            "change management",
            "consensus building",
            "proof of concept",
            "objective evaluation",
            "team buy-in"
        ],
        "common_mistakes": [
            "Dismissing team skepticism as resistance to change without understanding underlying concerns",
            "Adopting new tech merely because it is fashionable (resume-driven development)",
            "Forcing a top-down migration without adequate transition planning"
        ],
        "ideal_answer_points": [
            "Listened to the team's skepticism and documented their legitimate risk concerns (learning curve, migration cost)",
            "Conducted a low-risk spike or proof-of-concept project with measurable success criteria",
            "Presented data comparing maintenance cost, developer velocity, and performance gains",
            "Provided migration tooling, documentation, and brown-bag lunch learning sessions"
        ],
        "prerequisites": [
            "Engineering workflow experience"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "Describe a situation where a product manager requested a feature on an unrealistic deadline that would severely compromise code quality or reliability. How did you negotiate scope and expectations?",
        "topic": "Conflict Resolution & Collaboration",
        "subtopic": "Scope and Deadline Negotiation",
        "question_type": "conflict",
        "skill_type": "communication",
        "quality_tier": "core",
        "expected_concepts": [
            "scope negotiation",
            "trade-off management",
            "iron triangle (scope, time, quality)",
            "MVP phasing",
            "transparent communication"
        ],
        "common_mistakes": [
            "Saying a flat 'no' without proposing constructive alternatives",
            "Silently agreeing to the deadline and burning out or shipping buggy code",
            "Blaming product management for aggressive business deadlines"
        ],
        "ideal_answer_points": [
            "Explained technical risks and potential customer impact in business terms (outages, customer churn)",
            "Invoked the Iron Triangle: fixed deadline requires reducing scope or phased delivery",
            "Collaborated on an MVP Phase 1 with core high-value features for the deadline date",
            "Scheduled non-critical enhancements and technical hardening into Phase 2 follow-ups"
        ],
        "prerequisites": [
            "Agile delivery experience",
            "Product collaboration"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "easy",
        "question": "If a peer leaves critical or blunt comments on your pull request that feel dismissive, how do you handle the feedback constructively?",
        "topic": "Conflict Resolution & Collaboration",
        "subtopic": "Handling Code Review Feedback",
        "question_type": "situational",
        "skill_type": "communication",
        "quality_tier": "core",
        "expected_concepts": [
            "egoless programming",
            "emotional intelligence",
            "assumed positive intent",
            "in-person synchronization",
            "code quality standards"
        ],
        "common_mistakes": [
            "Taking code review comments as personal attacks and responding defensively or aggressively",
            "Ignoring feedback or merging around the reviewer without resolution",
            "Escalating trivial formatting debates into management complaints"
        ],
        "ideal_answer_points": [
            "Separate personal identity from code: critique of code is not critique of character",
            "Assume positive intent; text lacks tone and bluntness is rarely intended maliciously",
            "Clarify ambiguous feedback politely on the PR or take discussions to a quick huddle/call",
            "Evaluate suggestions objectively against team style guides and merge approved improvements"
        ],
        "prerequisites": [
            "Code review workflow experience"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "hard",
        "question": "Tell me about a time you had a major philosophical or strategic disagreement with your engineering manager or tech lead. How did you navigate the conversation and maintain a productive working relationship?",
        "topic": "Conflict Resolution & Collaboration",
        "subtopic": "Managing Disagreements Upward",
        "question_type": "conflict",
        "skill_type": "reasoning",
        "quality_tier": "advanced",
        "expected_concepts": [
            "managing up",
            "constructive dissent",
            "data-driven arguments",
            "disagree and commit",
            "professional relationship preservation"
        ],
        "common_mistakes": [
            "Undermining leadership authority in public team channels or behind their backs",
            "Continuing to resist or passively delay delivery after a formal decision is reached",
            "Abandoning all input and disengaging emotionally"
        ],
        "ideal_answer_points": [
            "Scheduled a private 1-on-1 to discuss technical concerns respectfully and candidly",
            "Prepared concrete evidence, benchmarks, or risk scenarios rather than abstract opinions",
            "Actively listened to leadership's broader business, organizational, and timeline constraints",
            "Committed fully once the final decision was made, demonstrating organizational maturity"
        ],
        "prerequisites": [
            "Engineering organizational dynamics"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "Describe an experience where two senior engineers on your team had opposing views on system architecture, stalling progress. How did you help facilitate a resolution?",
        "topic": "Conflict Resolution & Collaboration",
        "subtopic": "Mediating Architectural Impasses",
        "question_type": "conflict",
        "skill_type": "communication",
        "quality_tier": "core",
        "expected_concepts": [
            "conflict mediation",
            "decision matrices",
            "prototyping/spikes",
            "focusing on constraints",
            "consensus building"
        ],
        "common_mistakes": [
            "Taking sides based on personal friendship rather than technical merit",
            "Letting debates drag on for weeks without establishing a time-boxed decision mechanism",
            "Ignoring the underlying non-functional requirements driving both perspectives"
        ],
        "ideal_answer_points": [
            "Organized a structured session to map both proposals against non-functional requirements (latency, cost, scale)",
            "Created a decision evaluation matrix weighting team competencies and operational maintenance",
            "Proposed time-boxed prototyping spikes to test critical assumptions empirically with benchmarks",
            "Synthesized a compromise or guided the team toward a clear decision owner"
        ],
        "prerequisites": [
            "System architecture design",
            "Team facilitation"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "Walk me through a time when production requirements or project priorities shifted abruptly mid-sprint. How did you re-prioritize your deliverables without burning out?",
        "topic": "Delivery Under Pressure & Prioritization",
        "subtopic": "Mid-Sprint Priority Shifts",
        "question_type": "experience",
        "skill_type": "application",
        "quality_tier": "core",
        "expected_concepts": [
            "agile flexibility",
            "Eisenhower matrix",
            "sustainable pace",
            "stakeholder transparency",
            "scope pruning"
        ],
        "common_mistakes": [
            "Trying to accomplish both old and new requirements simultaneously by working unsustainable overtime",
            "Complaining about changes in direction rather than adapting productively",
            "Dropping in-flight tasks without documenting state or cleanly stashing branches"
        ],
        "ideal_answer_points": [
            "Paused to assess context and business rationale behind the incoming priority shift",
            "Cleanly committed and documented in-progress work to enable seamless resumption later",
            "Re-evaluated remaining sprint backlog with product owner, explicitly swapping out lower-priority commitments",
            "Communicated realistic revised delivery estimates to maintain high delivery quality"
        ],
        "prerequisites": [
            "Agile sprint delivery"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "easy",
        "question": "How do you manage your daily workflow and maintain focus on high-impact engineering tasks when constantly interrupted by ad-hoc Slack messages, alerts, and meetings?",
        "topic": "Delivery Under Pressure & Prioritization",
        "subtopic": "Focus Management and Context Switching",
        "question_type": "situational",
        "skill_type": "reasoning",
        "quality_tier": "core",
        "expected_concepts": [
            "deep work",
            "time blocking",
            "asynchronous communication",
            "triage and SLA",
            "burnout prevention"
        ],
        "common_mistakes": [
            "Treating all Slack messages as urgent interrupts requiring instant replies",
            "Attending optional meetings without agendas while falling behind on engineering deliverables",
            "Failing to set boundaries or communicate focus blocks"
        ],
        "ideal_answer_points": [
            "Scheduled dedicated 2-3 hour calendar blocks for deep programming and architectural focus",
            "Configured asynchronous communication habits: batching email/Slack checks between tasks",
            "Established clear team SLAs distinguishing urgent production incidents (P1 pager) from normal inquiries",
            "Automated alert deduplication to reduce operational noise and pager fatigue"
        ],
        "prerequisites": [
            "Professional time management"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "hard",
        "question": "Tell me about a time you had to release a feature with known technical debt or non-critical bugs to meet a critical business deadline. How did you assess the risk and ensure the debt was repaid?",
        "topic": "Delivery Under Pressure & Prioritization",
        "subtopic": "Deliberate Technical Debt Management",
        "question_type": "decision",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "advanced",
        "expected_concepts": [
            "pragmatic engineering",
            "technical debt backlog",
            "risk assessment",
            "business alignment",
            "debt repayment sprint"
        ],
        "common_mistakes": [
            "Shipping known technical debt without documenting it, letting it become permanent legacy code",
            "Refusing to ship valuable business features due to perfectionism",
            "Failing to obtain explicit stakeholder agreement for follow-up refactoring time"
        ],
        "ideal_answer_points": [
            "Assessed blast radius, probability of failure, and security implications of the shortcut",
            "Confirmed that known bugs were edge cases and did not threaten data integrity or security",
            "Documented the debt explicitly in issue tickets with clear architectural remediation steps",
            "Secured agreement from product leadership to schedule a technical debt sprint immediately post-launch"
        ],
        "prerequisites": [
            "Technical debt assessment",
            "Software lifecycle"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "Describe an instance where you discovered a critical bug hours before a major product launch. What steps did you take to evaluate severity and communicate options to stakeholders?",
        "topic": "Delivery Under Pressure & Prioritization",
        "subtopic": "Pre-Launch Critical Bug Escalation",
        "question_type": "experience",
        "skill_type": "reasoning",
        "quality_tier": "core",
        "expected_concepts": [
            "calm under pressure",
            "triage severity",
            "stakeholder escalation",
            "feature flagging",
            "go/no-go decision"
        ],
        "common_mistakes": [
            "Panicking and pushing an untested rushed hotfix minutes before launch",
            "Hiding the bug hoping users wouldn't discover it in production",
            "Canceling the launch unilaterally without consulting business leadership"
        ],
        "ideal_answer_points": [
            "Reproduced the issue systematically to understand blast radius and user impact",
            "Quickly gathered key stakeholders (Product, Engineering Lead, QA) for a go/no-go evaluation",
            "Presented options: (A) disable feature via feature flag and proceed with launch, (B) delay launch 24 hours for validated hotfix, or (C) ship with known mitigation",
            "Executed the agreed option calmly with comprehensive rollback procedures ready"
        ],
        "prerequisites": [
            "Production release management"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "Tell me about a time you made a significant technical mistake or caused an issue in production. What was the impact, how did you take accountability, and what did you implement to ensure it never happened again?",
        "topic": "Ownership, Failure & Accountability",
        "subtopic": "Production Mistakes and Accountability",
        "question_type": "failure",
        "skill_type": "reasoning",
        "quality_tier": "core",
        "expected_concepts": [
            "blameless post-mortem",
            "extreme ownership",
            "systemic prevention",
            "monitoring/guardrails",
            "incident remediation"
        ],
        "common_mistakes": [
            "Trying to minimize, hide, or blame the mistake on tooling or teammates",
            "Focusing only on personal apology rather than implementing systemic technical safeguards",
            "Allowing defensive embarrassment to slow down incident recovery"
        ],
        "ideal_answer_points": [
            "Immediately acknowledged the mistake in team channels and focused on restoring service",
            "Led a blameless post-mortem analyzing the sequence of events and failure of guardrails",
            "Avoided 'human error' as the root cause; recognized systemic process and tooling gaps",
            "Added automated integration tests, lint checks, CI gate validations, and improved monitoring alerts"
        ],
        "prerequisites": [
            "Production operations",
            "Post-mortem practices"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "easy",
        "question": "Describe a project or task where you received constructive criticism during a performance review or post-mortem. How did you act on that feedback to improve your work?",
        "topic": "Ownership, Failure & Accountability",
        "subtopic": "Receiving Constructive Feedback",
        "question_type": "experience",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "growth mindset",
            "receptiveness to feedback",
            "actionable improvement plan",
            "follow-up verification"
        ],
        "common_mistakes": [
            "Becoming defensive or dismissive of the feedback during the evaluation",
            "Giving a generic answer without explaining the specific corrective actions taken",
            "Failing to check back with the evaluator to verify observable progress"
        ],
        "ideal_answer_points": [
            "Listened openly without interrupting or making excuses, thanking the evaluator for the insight",
            "Reflected on the feedback and broke it down into tangible behavioral/technical goals",
            "Implemented specific daily routines or checks (e.g. better documentation, earlier design reviews)",
            "Followed up in subsequent 1-on-1s to review progress and ensure the improvement was sustained"
        ],
        "prerequisites": [
            "Professional self-awareness"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "hard",
        "question": "Describe a situation where a major engineering initiative you led failed to achieve its expected business goals or performance metrics. How did you conduct the post-mortem and what did you learn?",
        "topic": "Ownership, Failure & Accountability",
        "subtopic": "Project Failure and Retrospectives",
        "question_type": "failure",
        "skill_type": "reasoning",
        "quality_tier": "advanced",
        "expected_concepts": [
            "project retrospective",
            "KPI analysis",
            "validating assumptions early",
            "sunk cost fallacy",
            "institutional learning"
        ],
        "common_mistakes": [
            "Claiming to have never experienced a failed project or initiative",
            "Blaming marketing or sales entirely for the project's shortfall",
            "Falling into the sunk cost fallacy by continuing to invest in an unviable project"
        ],
        "ideal_answer_points": [
            "Led an objective, blameless retrospective analyzing differences between predicted vs actual metrics",
            "Discovered flawed upfront assumptions about user workflows or system scalability limits",
            "Decided collaboratively to sunset or pivot the feature rather than succumbing to sunk cost fallacy",
            "Documented key learnings and instituted user-testing checkpoints for future initiatives"
        ],
        "prerequisites": [
            "Engineering project leadership"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "Tell me about a time you made an architectural decision that you later realized was suboptimal. What new information changed your mind, and how did you pivot?",
        "topic": "Ownership, Failure & Accountability",
        "subtopic": "Architectural Pivots and Humility",
        "question_type": "decision",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "core",
        "expected_concepts": [
            "intellectual humility",
            "changing mind on evidence",
            "architectural migration",
            "cost-benefit analysis"
        ],
        "common_mistakes": [
            "Stubbornly defending an outdated decision despite mounting performance or maintainability issues",
            "Rewriting the architecture without a concrete migration and risk plan",
            "Blaming previous management for the initial architecture"
        ],
        "ideal_answer_points": [
            "Acknowledged that as data volume or business requirements grew, original trade-offs no longer held",
            "Benchmarked performance and maintenance costs under new scale to prove the bottleneck",
            "Communicated transparently with the team about why a pivot was necessary",
            "Designed an incremental zero-downtime migration to the revised architecture"
        ],
        "prerequisites": [
            "Architecture design experience"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "easy",
        "question": "How do you explain complex technical concepts or trade-offs (such as eventual consistency or database migration risks) to non-technical stakeholders or executive leadership?",
        "topic": "Communication & Mentorship",
        "subtopic": "Technical Communication for Non-Technical Audiences",
        "question_type": "experience",
        "skill_type": "communication",
        "quality_tier": "core",
        "expected_concepts": [
            "analogies and metaphors",
            "business impact focus",
            "avoiding jargon",
            "visual diagrams",
            "executive summaries"
        ],
        "common_mistakes": [
            "Using dense engineering jargon and acronyms that confuse business partners",
            "Focusing on internal implementation trivia rather than customer experience and business risks",
            "Impatient or condescending delivery when asked fundamental questions"
        ],
        "ideal_answer_points": [
            "Translate technical mechanisms into relatable business analogies (e.g. postal mail vs live telephone for async communication)",
            "Anchor discussions in business outcomes: revenue impact, customer trust, uptime, and compliance",
            "Use high-level visual diagrams showing user journeys rather than class diagrams",
            "Structure updates with bottom-line conclusion first (TL;DR), followed by trade-off options"
        ],
        "prerequisites": [
            "Stakeholder management"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "Describe a time when a critical project was falling behind schedule. How and when did you communicate this reality to leadership, and what mitigation plan did you propose?",
        "topic": "Communication & Mentorship",
        "subtopic": "Proactive Schedule Escalation",
        "question_type": "situational",
        "skill_type": "communication",
        "quality_tier": "core",
        "expected_concepts": [
            "early escalation",
            "bad news early",
            "mitigation options",
            "transparent tracking",
            "stakeholder trust"
        ],
        "common_mistakes": [
            "Waiting until the day before the deadline to announce that the project will be late",
            "Complaining about delays without bringing concrete remediation options to the table",
            "Hoping for a miracle rather than taking proactive control of the timeline"
        ],
        "ideal_answer_points": [
            "Surfaced the slip early as soon as velocity metrics indicated delivery risk ('bad news early')",
            "Analyzed root causes: unexpected legacy code complexity, unestimated external dependencies",
            "Presented leadership with viable trade-offs: defer secondary features, bring temporary assistance, or adjust date",
            "Restored stakeholder confidence through transparent daily burn-down tracking"
        ],
        "prerequisites": [
            "Project management",
            "Communication"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "Walk me through your philosophy and approach to conducting constructive, empathetic code reviews that uphold code quality while encouraging junior developers.",
        "topic": "Communication & Mentorship",
        "subtopic": "Empathetic Code Review Philosophy",
        "question_type": "experience",
        "skill_type": "communication",
        "quality_tier": "core",
        "expected_concepts": [
            "code review culture",
            "nit vs blocking comment",
            "asking questions over dictating",
            "celebrating good solutions",
            "automated style enforcement"
        ],
        "common_mistakes": [
            "Using code reviews as a display of intellectual dominance",
            "Burying real architectural flaws under dozens of subjective stylistic nitpicks",
            "Leaving vague, unhelpful comments like 'this is bad' without providing rationale or alternatives"
        ],
        "ideal_answer_points": [
            "Automate formatting and linting via CI tools so humans focus on architecture, correctness, and security",
            "Frame feedback as inquiries ('Have you considered X edge case?') rather than commands",
            "Label comments clearly: prefix with [Nit], [Question], or [Blocking] to clarify severity",
            "Praise elegant code and explain the 'why' behind architectural recommendations"
        ],
        "prerequisites": [
            "Code review workflow experience"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "hard",
        "question": "How do you handle communicating during a major live production outage with anxious customer-facing teams while engineers are actively troubleshooting under severe pressure?",
        "topic": "Communication & Mentorship",
        "subtopic": "Crisis Communication During Outages",
        "question_type": "situational",
        "skill_type": "communication",
        "quality_tier": "advanced",
        "expected_concepts": [
            "incident commander",
            "communications lead",
            "isolated war room",
            "cadence updates",
            "customer status page"
        ],
        "common_mistakes": [
            "Allowing dozens of customer-support reps to join the engineering war room and interrupt active debugging",
            "Giving unverified optimistic recovery promises ('it will be fixed in 5 minutes')",
            "Going completely silent for hours while diagnosing complex issues"
        ],
        "ideal_answer_points": [
            "Designate explicit roles: Incident Commander leads triage; dedicated Comms Lead handles external updates",
            "Keep technical troubleshooting war room focused and shielded from external interruptions",
            "Provide regular predictable status updates every 20-30 minutes, even if status is 'still investigating'",
            "Focus on facts: symptoms identified, current mitigation actions, and next scheduled update time"
        ],
        "prerequisites": [
            "Production incident management"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "easy",
        "question": "Tell me about a time you had to learn an unfamiliar programming language, framework, or domain from scratch under a tight deadline. What was your learning strategy?",
        "topic": "Career Growth & Adaptability",
        "subtopic": "Rapid Technical Learning",
        "question_type": "experience",
        "skill_type": "understanding",
        "quality_tier": "core",
        "expected_concepts": [
            "rapid skill acquisition",
            "first principles",
            "hands-on prototyping",
            "documentation navigation",
            "asking expert guidance"
        ],
        "common_mistakes": [
            "Spending weeks reading theoretical books without writing running code",
            "Hesitating to ask experienced teammates for architectural guidance",
            "Claiming expert mastery after only a few days of basic usage"
        ],
        "ideal_answer_points": [
            "Focused on fundamentals: syntax, concurrency model, standard libraries, and idiomatic conventions",
            "Built a toy prototype or small proof-of-concept to test core frameworks hands-on",
            "Consulted official documentation, open-source codebases, and conducted targeted pairing with domain experts",
            "Delivered the assigned feature on schedule while maintaining team code review standards"
        ],
        "prerequisites": [
            "Continuous learning mindset"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "Describe a situation where project requirements were highly ambiguous or undefined. How did you proactively discover requirements and make progress despite the ambiguity?",
        "topic": "Career Growth & Adaptability",
        "subtopic": "Navigating Ambiguous Requirements",
        "question_type": "situational",
        "skill_type": "reasoning",
        "quality_tier": "core",
        "expected_concepts": [
            "ambiguity",
            "requirements discovery",
            "stakeholder interviews",
            "prototyping/wireframes",
            "iterative delivery"
        ],
        "common_mistakes": [
            "Waiting idly for someone else to write complete requirements before doing any work",
            "Building an elaborate complex system based purely on unverified personal assumptions",
            "Becoming frustrated by changing requirements in early product stages"
        ],
        "ideal_answer_points": [
            "Scheduled discovery sessions with product, operations, and end-users to understand core pain points",
            "Documented explicit assumptions and draft user stories for stakeholder validation",
            "Created lightweight clickable prototypes or API schema contracts to make requirements tangible",
            "Delivered small iterative increments to gather fast customer feedback and refine direction"
        ],
        "prerequisites": [
            "Software development lifecycle"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "medium",
        "question": "Tell me about a time you received ambiguous or conflicting feedback from multiple stakeholders on how a system should behave. How did you reconcile the differences?",
        "topic": "Career Growth & Adaptability",
        "subtopic": "Reconciling Conflicting Feedback",
        "question_type": "experience",
        "skill_type": "reasoning",
        "quality_tier": "core",
        "expected_concepts": [
            "stakeholder alignment",
            "root cause desires",
            "facilitation",
            "trade-off clarification",
            "shared decision framework"
        ],
        "common_mistakes": [
            "Trying to satisfy all contradictory requests, creating an incoherent bloated system",
            "Silently picking one stakeholder's preference and alienating the other",
            "Escalating prematurely to executives without attempting team alignment"
        ],
        "ideal_answer_points": [
            "Brought the conflicting parties together in a collaborative alignment workshop",
            "Identified the underlying business objectives beneath their surface-level feature requests",
            "Framed options with objective trade-offs (e.g. speed to market vs customization depth)",
            "Helped the group converge on a unified solution aligned with primary business metrics"
        ],
        "prerequisites": [
            "Stakeholder negotiation"
        ]
    },
    {
        "category": "Behavioral",
        "difficulty": "hard",
        "question": "Describe a pivotal technical or career decision where you had to choose between staying in your comfort zone or taking on an unproven, high-risk technical challenge. What drove your choice?",
        "topic": "Career Growth & Adaptability",
        "subtopic": "Embracing High-Risk Challenges",
        "question_type": "decision",
        "skill_type": "tradeoff_analysis",
        "quality_tier": "advanced",
        "expected_concepts": [
            "calculated risk-taking",
            "career growth",
            "overcoming fear of failure",
            "ownership",
            "technical resilience"
        ],
        "common_mistakes": [
            "Choosing risks recklessly without evaluating personal or team blast radius",
            "Portraying oneself as having no hesitation or doubts",
            "Focusing only on the final outcome rather than the decision-making process and resilience developed"
        ],
        "ideal_answer_points": [
            "Evaluated the upside for personal/team growth against downside risk and developed fallback plans",
            "Recognized that staying in the comfort zone would lead to stagnation",
            "Embraced the ambiguity, invested significant effort in mastering the new domain, and persevered through initial setbacks",
            "Successfully delivered the project, accelerating team capabilities and technical confidence"
        ],
        "prerequisites": [
            "Professional career progression"
        ]
    }
]
