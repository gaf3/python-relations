"""
Unittest Tools for Relations
"""

# pylint: disable=unused-argument,arguments-differ

import relations

class MockSource(relations.Source):

    """
    Mock Source for Testing
    """

    ids = None  # ID's keyed by model names
    data = None # Data keyed by model names

    def __init__(self, name, **kwargs):

        self.ids = {}
        self.data = {}

    def field_init(self, field):
        """
        Make sure there's auto_increment
        """

        self.ensure_attribute(field, "auto_increment")

    def model_init(self, model):
        """
        Init the model
        """

        self.record_init(model._fields)

        # Even models without ids will have id's internally
        # They just won't be set in the model

        self.ids.setdefault(model.NAME, 0)
        self.data.setdefault(model.NAME, {})

        if model._id is not None and model._fields._names[model._id].auto_increment is None:
            model._fields._names[model._id].auto_increment = True
            model._fields._names[model._id].readonly = True

    def field_define(self, field, definitions):
        """
        define the field
        """
        definitions[field.store] = field.kind

    def model_define(self, cls):
        """
        define the model
        """

        model = cls.thy()

        definitions = {}

        self.record_define(model._fields, definitions)

        return {
            model.NAME: definitions
        }

    def model_create(self, model):
        """
        Executes the create
        """

        for creating in model._each("create"):

            values = creating._record.write({})

            self.ids[model.NAME] += 1

            if model._id is not None and values.get(model._id) is None:
                values[model._fields._names[model._id].store] = self.ids[model.NAME]
                creating[model._id] = self.ids[model.NAME]

            self.data[model.NAME][self.ids[model.NAME]] = values

            if not model._bulk:

                for parent_child in creating.CHILDREN:
                    if creating._children.get(parent_child):
                        creating._children[parent_child].create()

                creating._action = "update"
                creating._record._action = "update"

        if model._bulk:
            model._models = []
        else:
            model._action = "update"

        return model

    def model_like(self, model):
        """
        Gets the like matching records
        """

        parents = {}

        for field in model._label:
            for relation in model.PARENTS.values():
                if field == relation.child_field:
                    parent = relation.Parent.many(like=model._like).limit(model._chunk)
                    parents[model._fields._names[field].store] = parent[relation.parent_field]
                    model.overflow = model.overflow or parent.overflow

        likes = []

        for record in self.data[model.NAME].values():
            if model._record.match(record, model._label, model._like, parents):
                likes.append(record)

        return likes

    @staticmethod
    def model_sort(model):
        """
        Sorts the resuls
        """

        sort = model._sort or model._order

        if sort:
            model.sort(*sort)._sort = None

    @staticmethod
    def model_limit(model):
        """
        Limits the results
        """

        if model._limit is None:
            return

        model._models = model._models[model._offset:model._offset + model._limit]
        model.overflow = model.overflow or len(model._models) >= model._limit

    def model_retrieve(self, model, verify=True):
        """
        Executes the retrieve
        """

        model._collate()

        values = self.model_like(model) if model._like is not None else self.data[model.NAME].values()

        matches = []

        for record in values:
            if model._record.satisfy(record):
                matches.append(record)

        if model._mode == "one" and len(matches) > 1:
            raise relations.model.ModelError(model, "more than one retrieved")

        if model._mode == "one" and model._role != "child":

            if len(matches) < 1:

                if verify:
                    raise relations.model.ModelError(model, "none retrieved")

                return None

            model._record = model._build("update", _read=matches[0])

        else:

            model._models = []

            for match in matches:
                model._models.append(model.__class__(_read=match))

            model._record = None

        model._action = "update"

        if model._mode == "many":
            self.model_sort(model)
            self.model_limit(model)

        return model

    def field_update(self, field, values, changed=None):
        """
        Updates values with the field's that changed
        """

        if not field.readonly:
            if field.replace and not field.changed:
                field.value = field.default() if callable(field.default) else field.default
            if changed is None or field.changed == changed:
                values[field.store] = field.value
                field.changed = False

    def model_update(self, model):
        """
        Executes the update
        """

        updated = 0

        # If the overall model is retrieving and the record has values set

        if model._action == "retrieve" and model._record._action == "update":

            values = {}
            self.record_update(model._record, values, changed=True)

            for record in self.data[model.NAME].values():
                if model._record.satisfy(record):
                    updated += 1
                    record.update(values)

        elif model._id:

            for updating in model._each("update"):

                values = {}
                self.record_update(updating._record, values)

                self.data[model.NAME][updating[model._id]].update(values)

                updated += 1

                for parent_child in updating.CHILDREN:
                    if updating._children.get(parent_child):
                        updating._children[parent_child].create().update()

        else:

            raise relations.model.ModelError(model, "nothing to update from")

        return updated

    def model_delete(self, model):
        """
        Executes the delete
        """

        ids = []

        if model._action == "retrieve":

            for id, record in self.data[model.NAME].items():
                if model._record.satisfy(record):
                    ids.append(id)

        elif model._id:

            for deleting in model._each():
                ids.append(deleting[model._id])
                deleting._action = "create"

            model._action = "create"

        else:

            raise relations.model.ModelError(model, "nothing to delete from")

        for id in ids:
            del self.data[model.NAME][id]

        return len(ids)
