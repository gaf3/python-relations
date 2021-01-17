"""
Relations Module for handling models
"""

# pylint: disable=unsupported-membership-test,too-few-public-methods,too-many-branches,too-many-statements

import copy

import relations

class ModelError(Exception):
    """
    Generic model Error for easier tracing
    """

    def __init__(self, model, message):

        self.model = model
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        """
        Might want to mention the model and info about it
        """
        return f"{self.model.NAME}: {self.message}"

class ModelIdentity:
    """
    Intermiedate statuc type class for constructing mode information with a full model
    """

    SOURCE = None   # Data source

    NAME = None     # Name of the Model
    ID = 0          # Ref of id field (assumes first field)
    UNIQUE = None   # Unique indexes
    INDEX = None    # Regular indexes

    PARENTS = None  # Parent relationships (many/one to one)
    CHILDREN = None # Child relationships (one to many/one)
    SISTERS = None  # Sister relationships (many to many)
    BROTHERS = None # Brother relationships (many to many)

    _id = None     # Name of id field
    _fields = None # Base record to create other records with
    _unique = None # Actual unique indexes
    _index = None  # Actual indexes

    @classmethod
    def _thyself(cls, self=None):
        """
        Base identity to be known without instantiating the class
        """

        # If self wasn't sent, we're just providing a shell of an instance

        if self is None:
            self = ModelIdentity()
            self.__dict__.update(cls.__dict__)

        # Use NAME if set, else use class name

        setattr(self, 'NAME', cls.NAME or cls.__name__.lower())

        # Derive all the fields

        fields = relations.Record()

        for name, attribute in cls.__dict__.items():

            if name.startswith('_') or name != name.lower():
                continue # pragma: no cover

            if attribute in [bool, int, float, str, dict, list]:
                field = relations.Field(attribute)
            elif callable(attribute):
                field = relations.Field(type(attribute()), default=attribute)
            elif isinstance(attribute, list):
                field = relations.Field(type(attribute[0]), options=attribute)
            elif isinstance(attribute, tuple):
                field = relations.Field(*attribute)
            elif isinstance(attribute, dict):
                field = relations.Field(**attribute)
            elif isinstance(attribute, relations.Field):
                field = attribute
            else:
                continue # pragma: no cover

            field.name = name

            fields.append(field)

        setattr(self, '_fields', fields)

        # Determine the _id field name

        if cls.ID is not None:
            setattr(self, '_id', self._field_name(cls.ID))

        # Figure out indexes

        unique = self.UNIQUE

        if unique is None:
            unique = []
            for field in self._fields._order:
                if self._id == field.name:
                    continue
                if field.kind in (int, str):
                    unique.append(field.name)
                if field.kind == str:
                    break
        elif not unique:
            unique = {}

        if isinstance(unique, str):
            unique = [unique]

        if isinstance(unique, list):
            unique = {
                "-".join(unique): unique
            }

        if isinstance(unique, dict):
            self._unique = unique

        # Make sure all the unique indexes check out

        for unique in self._unique:
            for field in self._unique[unique]:
                if field not in self._fields:
                    raise ModelError(self, f"cannot find field {field} from unique {unique}")

        index = self.INDEX or {}

        if isinstance(index, str):
            index = [index]

        if isinstance(index, list):
            index = {
                "-".join(index): index
            }

        if isinstance(index, dict):
            self._index = index

        # Make sure all the indexes check out

        for index in self._index:
            for field in self._index[index]:
                if field not in self._fields:
                    raise ModelError(self, f"cannot find field {field} from index {index}")

        # Initialize relation models

        self.PARENTS = cls.PARENTS or {}
        self.CHILDREN = cls.CHILDREN or {}
        self.SISTERS = cls.SISTERS or {}
        self.BROTHERS = cls.BROTHERS or {}

        # Have the the source do whatever it needs to

        if relations.source(cls.SOURCE) is not None:
            relations.source(cls.SOURCE).model_init(self)

        return self

    def _field_name(self, field):
        """
        Returns the name of the field, whether index or name
        """

        if field not in self._fields:
            raise ModelError(self, f"cannot find field {field} in {self.NAME}")

        if isinstance(field, str):
            return field

        return self._fields._order[field].name

class Model(ModelIdentity):
    """
    Main model class
    """

    _record = None # The current loaded single record (from get/create)
    _models = None # The current loaded multiple models (from list/create)

    _parents = None  # Parent models
    _children = None # Children models
    _sisters = None  # Sister models
    _brothers = None # Brother models

    _role = None     # Whether we're a model, parent or child
    _mode = None     # Whether we're dealing with one or many
    _action = None   # Overall action of this model
    _related = None  # Which fields will be set automatically

    @staticmethod
    def _extract(kwargs, name, default=None):
        """
        Grabs and remove a value from kwargs so we can chain properly
        """

        if name in kwargs:
            value = kwargs[name]
            del kwargs[name]
            return value

        return default

    def __init__(self, *args, **kwargs):
        """
        Creation is implied but we want to set stuff and call create impliicitly
        """

        # Know thyself

        self._thyself(self)

        # Initialize relation models

        self._parents = {}
        self._children = {}
        self._sisters = {}
        self._brothers = {}
        self._related = {}

        # Making things and explicit, we're going to derive a lot defaults from
        # context of what the user sent in

        # If a child's been sent in, we're a parent and we're retrieving as one

        _read = self._extract(kwargs, '_read')
        _child = self._extract(kwargs, '_child')
        _parent = self._extract(kwargs, '_parent')

        # Now just assume things were sent explicitly and we might override them
        # later because the logic here is pretty hairy

        self._role = "model"
        self._action = self._extract(kwargs, '_action', "create")

        # If we're being created from reading from a source

        if _read is not None:

            self._mode = "one"
            self._action = "update"
            self._record = self._build(self._action, _read=_read)

        # If we're being created as a parent

        elif _child is not None:

            self._related = _child
            self._role = "parent"
            self._mode = "one"
            self._action = "retrieve"

            self._record = self._build(self._action, _defaults=False)
            self.filter(*args, **kwargs)

        # If we being created as a child

        elif _parent is not None:

            self._related = _parent
            self._role = "child"
            self._mode = self._extract(kwargs, '_mode')
            self._action = "retrieve" if list(self._related.values())[0] is not None else "create"

            if self._action == "retrieve":
                self._record = self._build(self._action, _defaults=False)
                self.filter(*args, **kwargs)

        # If we're being created as a search

        elif self._action == "retrieve":

            self._mode = self._extract(kwargs, '_mode')
            self._record = self._build(self._action, _defaults=False)
            self.filter(*args, **kwargs)

        # IF we're just being straight up (now tell me) created

        elif self._action == "create":

            self._mode = self._extract(kwargs, '_mode', "many" if args and isinstance(args[0], list) else "one")
            self._related = self._extract(kwargs, '_related', {})

            if self._mode == "many":

                self._models = []

                for each in args[0]:
                    eargs = each if isinstance(each, list) else []
                    ekwargs = each if isinstance(each, dict) else {}
                    self._models.append(self.__class__(*eargs, **ekwargs))

            else:

                self._record = self._build(self._action, *args, **kwargs)

    def __setattr__(self, name, value):
        """
        Use to set field values directly
        """

        if name[0] != '_' and name == name.lower() and name in (object.__getattribute__(self, '_fields') or []):

            self._ensure()

            if self._role == "child" and self._mode == "one":
                if self._models:
                    setattr(self._models[0], name, value)
                else:
                    raise ModelError(self, "no record")
            elif self._mode == "one":
                self._record[name] = value
                self._propagate(name, value)
            else:
                if self._models:
                    for model in self._models:
                        setattr(model, name, value)
                else:
                    raise ModelError(self, "no records")

        else:

            object.__setattr__(self, name, value)

    def __getattr__(self, name):
        """
        Used to get relation models directly
        """

        if name in self.PARENTS or name in self.CHILDREN:

            self._ensure()

            if self._mode == "one":
                return self._relate(name)

        raise AttributeError(f"'{self}' object has no attribute '{name}'")

    def __getattribute__(self, name):
        """
        Use to get field values directly
        """

        if name[0] != '_' and name == name.lower() and name in (object.__getattribute__(self, '_fields') or []):

            self._ensure()

            if self._role == "child" and self._mode == "one":
                if self._models:
                    return getattr(self._models[0], name)
                raise ModelError(self, "no record")

            if self._mode == "one":
                return self._record[name]

            if not self._models:
                raise ModelError(self, "no records")

            return [getattr(model, name) for model in self._models]

        return object.__getattribute__(self, name)

    def __len__(self):
        """
        Use for numnber of record
        """

        self._ensure()

        if self._role == "child" and self._mode == "one":
            if self._models:
                return len(self._models[0])
            return 0

        if self._mode == "one":
            return len(self._record)

        return len(self._models)

    def __iter__(self):
        """
        Use the order of record
        """

        self._ensure()

        if self._role == "child" and self._mode == "one":
            if self._models:
                return iter(self._models[0])
            return iter([])

        if self._mode == "one":
            return iter(self._record)

        return iter(self._models)

    def keys(self):
        """
        Use the order of record
        """

        self._ensure()

        if self._mode == "many":
            raise ModelError(self, "no keys with many")

        if self._role == "child":
            if self._models:
                return iter(self._models[0]._record._names)
            return iter([])
        return iter(self._record._names)

    def __contains__(self, key):
        """
        Checks numerically or by name
        """

        self._ensure()

        if self._role == "child" and self._mode == "one":

            if self._models:
                return key in self._models[0]

            return False

        if self._mode == "one":
            return key in self._record

        if self._models:
            return key in self._fields

        return False

    def __setitem__(self, key, value):
        """
        Access numerically or by name
        """

        self._ensure()

        if self._role == "child" and self._mode == "one":
            if self._models:
                self._models[0][key] = value
            else:
                raise ModelError(self, "no record")
        elif self._mode == "one":
            self._record[key] = value
            self._propagate(key, value)
        else:
            if isinstance(key, int):
                raise ModelError(self, "no override")
            if self._models:
                for model in self._models:
                    model[key] = value
            else:
                raise ModelError(self, "no records")

    def __getitem__(self, key):
        """
        Access numerically or by name
        """

        self._ensure()

        if self._role == "child" and self._mode == "one":
            if self._models:
                return self._models[0][key]
            raise ModelError(self, "no record")

        if self._mode == "one":
            return self._record[key]

        if not self._models:
            raise ModelError(self, "no records")

        if isinstance(key, int):
            return self._models[key]

        return [model[key] for model in self._models]

    @classmethod
    def _parent(cls, relation):
        """
        Adds a parent to the class
        """

        cls.PARENTS = cls.PARENTS or {}
        cls.PARENTS[relation.child_parent] = relation

    @classmethod
    def _child(cls, relation):
        """
        Adds a child to the class
        """

        cls.CHILDREN = cls.CHILDREN or {}
        cls.CHILDREN[relation.parent_child] = relation

    @classmethod
    def _sister(cls, relation):
        """
        Adds a sister to the class
        """

        cls.SISTERS = cls.SISTERS or {}
        cls.SISTERS[relation.brother_sister] = relation

    @classmethod
    def _brother(cls, relation):
        """
        Adds a brother to the class
        """

        cls.BROTHERS = cls.BROTHERS or {}
        cls.BROTHERS[relation.sister_brother] = relation

    def _relate(self, name):
        """
        Looks up a relation by attribute name
        """

        if name in self.PARENTS: # pylint: disable=no-else-return

            relation = self.PARENTS[name]

            if self._parents.get(name) is None:
                if self._action == "retrieve":
                    self._parents[name] = relation.Parent.many()
                else:
                    self._parents[name] = relation.Parent(_child={relation.parent_field: self[relation.child_field]})

            return self._parents[name]

        elif name in self.CHILDREN:

            relation = self.CHILDREN[name]

            if self._children.get(name) is None:
                if self._action == "retrieve":
                    self._children[name] = relation.Child.many()
                else:
                    self._children[name] = relation.Child(
                        _parent={relation.child_field: self._record[relation.parent_field]}, _mode=relation.MODE
                    )

            return self._children[name]

        return None

    def _collate(self):
        """
        Executes relatives criteria and adds to our own
        """

        for child_parent, relation in self.PARENTS.items():
            if self._parents.get(child_parent) is not None:
                self._record.filter(f"{relation.child_field}__in", self._parents[child_parent][relation.parent_field])

        for parent_child, relation in self.CHILDREN.items():
            if self._children.get(parent_child) is not None:
                self._record.filter(f"{relation.parent_field}__in", self._children[parent_child][relation.child_field])

    def _propagate(self, field, value):
        """
        Remove a relation when its field is set or reset a parent field
        """

        field_name = self._field_name(field)

        if field_name in self._related:
            self._related[field_name] = value

        for child_parent, relation in self.PARENTS.items():
            if field_name == relation.child_field:
                self._parents[child_parent] = None

        for parent_child, relation in self.CHILDREN.items():
            if field_name == relation.parent_field and self._relate(parent_child):
                self._relate(parent_child)[relation.child_field] = value

    def _input(self, record, *args, **kwargs):
        """
        Fills in field values from args, kwargs
        """

        field = 0

        for value in args:
            while record._order[field].readonly or record._order[field].name in self._related:
                field += 1
            record[field] = value
            field += 1

        for name, value in kwargs.items():
            record[name] = value

    def _build(self, _action, *args, **kwargs):
        """
        Fills in record
        """

        _defaults = self._extract(kwargs, '_defaults', True)
        _read = self._extract(kwargs, '_read')

        record = copy.deepcopy(self._fields)
        record._action = _action

        if _defaults:
            for field in record._order:
                if field.default is not None:
                    field.value = field.default() if callable(field.default) else field.default

        if _read is not None:
            record.read(_read)

        for field, value in self._related.items():
            record[field] = value

        self._input(record, *args, **kwargs)

        return record

    def _ensure(self):
        """
        Makes sure there's records if there's criteria
        """

        if self._action == "retrieve":
            if self._record._action == "update":
                raise ModelError(self, "need to update")
            self.retrieve()

    def _each(self, action=None):
        """
        Converts to all models, whether _record or _models
        """

        if self._record and (action is None or self._action == action):
            return [self]

        if self._models:
            return [model for model in self._models if action is None or model._action == action]

        return []

    def filter(self, *args, **kwargs):
        """
        Sets to return multiple records
        """

        for field, value in self._related.items():
            self._record.filter(field, value)

        for index, value in enumerate(args):
            self._record.filter(index, value)

        for name, value in kwargs.items():

            pieces = name.split('__', 1)

            relation = self._relate(pieces[0])

            if relation is not None:
                relation.filter(**{pieces[1]: value})
            else:
                self._record.filter(name, value)

        return self

    @classmethod
    def one(cls, *args, **kwargs):
        """
        For retrieving a single record
        """

        return cls(_action="retrieve", _mode="one", *args, **kwargs)

    @classmethod
    def many(cls, *args, **kwargs):
        """
        Sets to return multiple records
        """

        return cls(_action="retrieve", _mode="many", *args, **kwargs)

    def set(self, *args, **kwargs):
        """
        Sets a single or multiple records or prepares to
        """

        # If we're retrieving, make we're only getting one or we'll store
        if self._action == "retrieve":
            if self._mode == "one":
                self.retrieve()
            else:
                self._record._action = "update"

        for model in self._each():
            self._input(model._record, *args, **kwargs)

        return self

    def add(self, *args, **kwargs):
        """
        Adds records
        """

        self._ensure()

        _count = self._extract(kwargs, '_count', 1)

        if self._role == "child" and self._mode == "one":

            if self._models or _count > 1:
                raise ModelError(self, "only one allowed")

            self._models = [
                self.__class__(_action="create", _related=self._related, *args, **kwargs)
            ]

        elif self._mode == "one":

            raise ModelError(self, "only one allowed")

        else:

            if self._models is None:
                self._models = []

            for _ in range(_count):
                self._models.append(self.__class__(_action="create", _related=self._related, *args, **kwargs))

        return self

    @classmethod
    def define(cls, *args, **kwargs):
        """
        define the model
        """
        return relations.source(cls.SOURCE).model_define(cls, *args, **kwargs)

    def create(self, *args, **kwargs):
        """
        create the model
        """

        if self._action not in ["create", "update"]:
            raise ModelError(self, f"cannot create during {self._action}")

        return relations.source(self.SOURCE).model_create(self, *args, **kwargs)

    def retrieve(self, verify=True, *args, **kwargs):
        """
        retrieve the model
        """

        if self._action != "retrieve":
            raise ModelError(self, f"cannot retrieve during {self._action}")

        return relations.source(self.SOURCE).model_retrieve(self, verify, *args, **kwargs)

    def update(self, *args, **kwargs):
        """
        update the model
        """

        if self._action not in ["update", "retrieve"]:
            raise ModelError(self, f"cannot update during {self._action}")

        return relations.source(self.SOURCE).model_update(self, *args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        delete the model
        """

        if self._action not in ["update", "retrieve"]:
            raise ModelError(self, f"cannot delete during {self._action}")

        if self._action == "retrieve" and self._mode == "one":
            self.retrieve()

        return relations.source(self.SOURCE).model_delete(self, *args, **kwargs)
